from __future__ import annotations

from urllib.parse import urlparse

from intel_platform.collection.crawler import crawl_urls


def _validate_url(url: str) -> None:
    """SSRF protection: reject non-HTTP schemes and private network URLs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or \
       hostname.startswith("169.254.") or hostname.startswith("10.") or \
       hostname.startswith("192.168."):
        raise ValueError("URLs pointing to internal/private networks are not allowed")


class WebScraper:
    """Scrape a single URL using crawl4ai's headless browser."""

    async def scrape_url(self, url: str, timeout: float = 30) -> dict:
        _validate_url(url)
        docs = await crawl_urls([url], timeout_ms=int(timeout * 1000))
        if not docs:
            raise RuntimeError(f"Failed to crawl {url}")
        doc = docs[0]
        return {
            "url": doc["url"],
            "title": doc["title"],
            "content": doc["content"],
            "content_length": len(doc["content"]),
        }
