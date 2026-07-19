"""Web scrape connector — fetches and extracts text from web pages.

Wraps the existing WebScraper + ProxiedClient infrastructure.
"""
from __future__ import annotations

from datetime import datetime, timezone

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.collection.scraper import WebScraper
from intel_platform.connectors.base import (
    AcquireResult,
    ConnectorHealth,
    HealthStatus,
    SourceConnector,
    register_connector,
)


@register_connector
class WebScrapeConnector(SourceConnector):
    """Scrape web pages and extract text content for intelligence analysis."""

    source_type = "web_scrape"

    def configure(self, config: dict) -> dict:
        url = config.get("url", "").strip()
        if not url:
            raise ValueError("'url' is required for web_scrape sources")
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL must use http or https scheme, got: {parsed.scheme}")
        return {
            "url": url,
            "selectors": config.get("selectors", []),
            "max_pages": min(int(config.get("max_pages", 1)), 50),
            "headers": config.get("headers", {}),
            "timeout": float(config.get("timeout", 30)),
        }

    async def test(self, config: dict) -> HealthStatus:
        try:
            client = ProxiedClient()
            resp = await client.get(config["url"], timeout=config.get("timeout", 15))
            if resp.status_code < 400:
                return HealthStatus(status=ConnectorHealth.HEALTHY)
            return HealthStatus(status=ConnectorHealth.DEGRADED, last_error=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error=str(e))

    async def acquire(self, config: dict, since: datetime | None = None) -> AcquireResult:
        url = config.get("url", "")
        if not url:
            return AcquireResult(success=False, error="No URL configured")

        scraper = WebScraper()
        timeout = config.get("timeout", 30)
        selectors = config.get("selectors", [])

        try:
            result = await scraper.scrape_url(url, timeout=timeout)
            content = result.get("content", "")
            title = result.get("title", "")

            # If CSS selectors provided, re-fetch and extract only matching elements
            if selectors and content:
                from bs4 import BeautifulSoup
                client = ProxiedClient()
                html = await client.fetch_text(url, timeout=timeout)
                soup = BeautifulSoup(html, "html.parser")
                selected_parts = []
                for sel in selectors:
                    for el in soup.select(sel):
                        selected_parts.append(el.get_text(separator="\n", strip=True))
                if selected_parts:
                    content = "\n\n".join(selected_parts)

            records = [{
                "url": url,
                "title": title,
                "content": content,
                "content_length": len(content),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }]

            return AcquireResult(
                success=True,
                record_count=1,
                records=records,
                metadata={"source_url": url, "title": title},
            )
        except Exception as e:
            return AcquireResult(success=False, error=str(e), metadata={"source_url": url})
