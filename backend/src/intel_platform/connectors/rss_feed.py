"""RSS/Atom feed connector — fetches and parses syndicated content.

Supports incremental collection via the `since` parameter and
optional full-content fetching by following article links.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime

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


@register_connector
class RSSFeedConnector(SourceConnector):
    """Fetch and parse RSS/Atom feeds for intelligence collection."""

    source_type = "rss_feed"
    config_keys = ("feed_url",)
    capability_note = (
        "Fetches a public RSS/Atom feed. Needs the feed URL itself, not the site "
        "homepage."
    )

    def configure(self, config: dict) -> dict:
        feed_url = config.get("feed_url", "").strip()
        if not feed_url:
            raise ValueError("'feed_url' is required for rss_feed sources")
        from urllib.parse import urlparse
        parsed = urlparse(feed_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Feed URL must use http or https, got: {parsed.scheme}")
        return {
            "feed_url": feed_url,
            "max_items": min(int(config.get("max_items", 50)), 500),
            "fetch_full_content": bool(config.get("fetch_full_content", False)),
        }

    async def test(self, config: dict) -> HealthStatus:
        try:
            import feedparser
            client = ProxiedClient()
            text = await client.fetch_text(config["feed_url"], timeout=15)
            feed = feedparser.parse(text)
            if feed.bozo and not feed.entries:
                return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error="Invalid feed format")
            return HealthStatus(status=ConnectorHealth.HEALTHY)
        except ImportError:
            return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error="feedparser not installed")
        except Exception as e:
            return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error=str(e))

    async def acquire(self, config: dict, since: datetime | None = None) -> AcquireResult:
        feed_url = config.get("feed_url", "")
        if not feed_url:
            return AcquireResult(success=False, error="No feed URL configured")

        try:
            import feedparser
        except ImportError:
            return AcquireResult(success=False, error="feedparser not installed: pip install feedparser")

        max_items = config.get("max_items", 50)
        fetch_full = config.get("fetch_full_content", False)

        try:
            client = ProxiedClient()
            text = await client.fetch_text(feed_url, timeout=30)
            feed = feedparser.parse(text)

            if feed.bozo and not feed.entries:
                return AcquireResult(success=False, error=f"Feed parse error: {feed.bozo_exception}")

            records = []
            scraper = WebScraper() if fetch_full else None

            for entry in feed.entries[:max_items]:
                # Parse publication date
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published_at = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
                    except (ValueError, OverflowError):
                        pass

                # Incremental: skip entries older than `since`
                if since and published_at and published_at <= since:
                    continue

                # Get content: summary/description from feed
                content = ""
                if hasattr(entry, "content") and entry.content:
                    content = entry.content[0].get("value", "")
                elif hasattr(entry, "summary"):
                    content = entry.summary or ""
                elif hasattr(entry, "description"):
                    content = entry.description or ""

                # Strip HTML from content
                if content and "<" in content:
                    from bs4 import BeautifulSoup
                    content = BeautifulSoup(content, "html.parser").get_text(separator="\n", strip=True)

                # Optionally fetch full article content
                link = getattr(entry, "link", "")
                if fetch_full and link and scraper:
                    try:
                        full = await scraper.scrape_url(link, timeout=15)
                        content = full.get("content", content)
                    except Exception as e:
                        logger.debug("Failed to fetch full content for %s: %s", link, e)

                title = getattr(entry, "title", "")
                records.append({
                    "title": title,
                    "url": link,
                    "content": content,
                    "published_at": published_at.isoformat() if published_at else "",
                    "feed_url": feed_url,
                })

            return AcquireResult(
                success=True,
                record_count=len(records),
                records=records,
                metadata={"feed_url": feed_url, "feed_title": getattr(feed.feed, "title", "")},
            )
        except Exception as e:
            return AcquireResult(success=False, error=str(e), metadata={"feed_url": feed_url})
