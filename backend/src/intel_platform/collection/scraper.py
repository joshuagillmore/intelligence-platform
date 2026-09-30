from __future__ import annotations

from intel_platform.collection.crawler import crawl_urls
from intel_platform.collection.url_guard import validate_url


class WebScraper:
    """Scrape a single URL using crawl4ai's headless browser."""

    async def scrape_url(self, url: str, timeout: float = 30) -> dict:
        # Validate up front so a single bad URL raises rather than silently
        # returning nothing; crawl_urls also validates every URL it fetches.
        validate_url(url)
        rejected: list[tuple[str, str]] = []
        docs = await crawl_urls([url], timeout_ms=int(timeout * 1000), rejected=rejected)
        if not docs:
            if rejected:
                # Say why: "failed" and "refused by the SSRF guard" are not the
                # same event, and the activity trail should show which it was.
                raise RuntimeError(f"Rejected {url}: {rejected[0][1]}")
            raise RuntimeError(f"Failed to crawl {url}")
        doc = docs[0]
        return {
            "url": doc["url"],
            "title": doc["title"],
            "content": doc["content"],
            "content_length": len(doc["content"]),
        }
