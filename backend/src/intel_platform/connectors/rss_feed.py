"""RSS/Atom feed connector — fetches feed items and optionally scrapes full content."""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.collection.scraper import WebScraper
from intel_platform.connectors.base import (
    AcquireResult,
    ConnectorHealth,
    HealthStatus,
    SourceConnector,
    register_connector,
)

logger = logging.getLogger(__name__)


def _parse_feed_items(xml_text: str, max_items: int = 20) -> list[dict]:
    """Parse RSS 2.0 or Atom feed XML into item dicts."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("Failed to parse feed XML: %s", e)
        return []

    # RSS 2.0: <rss><channel><item>
    rss_items = root.findall(".//item")
    if rss_items:
        for item in rss_items[:max_items]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            items.append({
                "title": title,
                "link": link,
                "description": desc,
                "published": pub_date,
            })
        return items

    # Atom: <feed><entry>
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//atom:entry", ns)
    # Also try without namespace
    if not entries:
        entries = root.findall(".//entry")

    for entry in entries[:max_items]:
        title = (entry.findtext("atom:title", "", ns) or entry.findtext("title", "")).strip()
        link_el = entry.find("atom:link", ns) or entry.find("link")
        link = (link_el.get("href", "") if link_el is not None else "").strip()
        summary = (entry.findtext("atom:summary", "", ns) or entry.findtext("summary", "")).strip()
        published = (entry.findtext("atom:published", "", ns) or entry.findtext("published", "")).strip()
        items.append({
            "title": title,
            "link": link,
            "description": summary,
            "published": published,
        })

    return items


@register_connector
class RSSFeedConnector(SourceConnector):
    """Connector for RSS/Atom feeds.

    Config schema:
        {
            "feed_url": "https://example.com/rss",
            "max_items": 20,
            "fetch_full_content": true
        }
    """

    source_type = "rss_feed"

    def configure(self, config: dict[str, Any]) -> dict[str, Any]:
        feed_url = config.get("feed_url", "")
        if not feed_url:
            raise ValueError("'feed_url' is required")
        return {
            "feed_url": feed_url,
            "max_items": int(config.get("max_items", 20)),
            "fetch_full_content": bool(config.get("fetch_full_content", True)),
        }

    async def test(self, config: dict[str, Any]) -> HealthStatus:
        feed_url = config.get("feed_url", "")
        if not feed_url:
            return HealthStatus(status=ConnectorHealth.UNKNOWN, last_error="No feed URL configured")
        client = ProxiedClient()
        try:
            xml_text = await client.fetch_text(feed_url, timeout=15)
            items = _parse_feed_items(xml_text, max_items=1)
            if items:
                return HealthStatus(status=ConnectorHealth.HEALTHY)
            return HealthStatus(status=ConnectorHealth.DEGRADED, last_error="Feed parsed but no items found")
        except Exception as e:
            return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error=str(e))

    async def acquire(self, config: dict[str, Any], since: datetime | None = None) -> AcquireResult:
        feed_url = config.get("feed_url", "")
        max_items = config.get("max_items", 20)
        fetch_full = config.get("fetch_full_content", True)

        if not feed_url:
            return AcquireResult(success=False, error="No feed URL configured")

        # Fetch and parse feed
        client = ProxiedClient()
        try:
            xml_text = await client.fetch_text(feed_url, timeout=30)
        except Exception as e:
            return AcquireResult(success=False, error=f"Failed to fetch feed: {e}")

        items = _parse_feed_items(xml_text, max_items=max_items)
        if not items:
            return AcquireResult(success=True, record_count=0, records=[],
                                error="Feed parsed but contained no items")

        logger.info("Parsed %d items from feed %s", len(items), feed_url)

        records = []
        errors = []

        for item in items:
            record = {
                "url": item["link"],
                "title": item["title"],
                "content": item["description"],
                "content_length": len(item["description"]),
                "published": item["published"],
                "source_feed": feed_url,
            }

            # Optionally fetch full article content
            if fetch_full and item["link"]:
                try:
                    scraper = WebScraper()
                    full = await scraper.scrape_url(item["link"], timeout=20)
                    if full.get("content") and len(full["content"]) > len(item["description"]):
                        record["content"] = full["content"]
                        record["content_length"] = full["content_length"]
                    await asyncio.sleep(0.5)  # Rate limit
                except Exception as e:
                    logger.debug("Could not fetch full content for %s: %s", item["link"], e)
                    errors.append(f"{item['link']}: {e}")

            if record["content"]:
                records.append(record)

        return AcquireResult(
            success=len(records) > 0,
            record_count=len(records),
            records=records,
            error="; ".join(errors[:5]) if errors else "",
        )
