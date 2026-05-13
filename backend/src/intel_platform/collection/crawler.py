from __future__ import annotations

import logging
from typing import Callable

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

logger = logging.getLogger(__name__)

_browser_cfg = BrowserConfig(headless=True, browser_type="chromium")


def _make_run_cfg(timeout_ms: int = 30000) -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=50,
        page_timeout=timeout_ms,
    )


async def crawl_urls(
    urls: list[str],
    timeout_ms: int = 30000,
    on_progress: Callable[[str, str], None] | None = None,
) -> list[dict]:
    """Crawl a list of URLs with headless Chromium and return structured documents.

    Args:
        urls: URLs to crawl.
        timeout_ms: Per-page timeout in milliseconds.
        on_progress: Optional callback(url, status) for progress tracking.

    Returns:
        List of document dicts with url, title, content, markdown, word_count, links.
    """
    if not urls:
        return []

    run_cfg = _make_run_cfg(timeout_ms)
    documents = []

    async with AsyncWebCrawler(config=_browser_cfg) as crawler:
        results = await crawler.arun_many(urls=urls, config=run_cfg)

        for result in results:
            if not result.success:
                logger.warning("Crawl failed for %s: %s", result.url, result.error_message)
                if on_progress:
                    on_progress(result.url, "error")
                continue

            raw_md = result.markdown.raw_markdown if result.markdown else ""
            fit_md = result.markdown.fit_markdown if result.markdown else ""
            content = fit_md or raw_md
            meta = result.metadata or {}
            links = result.links or {}

            documents.append({
                "url": result.url,
                "title": meta.get("title", ""),
                "content": content,
                "raw_markdown": raw_md,
                "word_count": len(content.split()) if content else 0,
                "links_internal": len(links.get("internal", [])),
                "links_external": len(links.get("external", [])),
            })

            if on_progress:
                on_progress(result.url, "done")

    return documents
