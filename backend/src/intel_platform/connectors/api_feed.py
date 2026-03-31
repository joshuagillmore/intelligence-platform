"""API feed connector — treats API/data feed sources as web scrapes.

For sources like threat intel feeds, procurement APIs, etc., the LLM resolves
them to publicly accessible web URLs which are then scraped.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

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
class APIFeedConnector(SourceConnector):
    """Connector for API feeds and data services.

    Config schema:
        {
            "urls": ["https://example.com/api/data", ...],
            "max_pages": 10
        }
    """

    source_type = "api_feed"

    def configure(self, config: dict[str, Any]) -> dict[str, Any]:
        urls = config.get("urls", [])
        if not isinstance(urls, list):
            raise ValueError("'urls' must be a list of URL strings")
        return {"urls": urls, "max_pages": int(config.get("max_pages", 10))}

    async def test(self, config: dict[str, Any]) -> HealthStatus:
        urls = config.get("urls", [])
        if not urls:
            return HealthStatus(status=ConnectorHealth.UNKNOWN, last_error="No URLs configured")
        scraper = WebScraper()
        try:
            await scraper.scrape_url(urls[0], timeout=10)
            return HealthStatus(status=ConnectorHealth.HEALTHY)
        except Exception as e:
            return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error=str(e))

    async def acquire(self, config: dict[str, Any], since: datetime | None = None) -> AcquireResult:
        urls = config.get("urls", [])
        max_pages = config.get("max_pages", 10)

        if not urls:
            return AcquireResult(success=True, record_count=0, records=[])

        scraper = WebScraper()
        records = []
        errors = []

        for url in urls[:max_pages]:
            try:
                result = await scraper.scrape_url(url, timeout=30)
                if result.get("content"):
                    records.append(result)
                    logger.info("Fetched API/feed %s (%d chars)", url, result.get("content_length", 0))
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", url, e)
                errors.append(f"{url}: {e}")

            if url != urls[-1]:
                await asyncio.sleep(1)

        return AcquireResult(
            success=len(records) > 0 or len(errors) == 0,
            record_count=len(records),
            records=records,
            error="; ".join(errors) if errors else "",
        )
