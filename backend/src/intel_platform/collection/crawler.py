from __future__ import annotations

import logging
from typing import Callable

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai import ProxyConfig as Crawl4aiProxyConfig

from intel_platform.collection.proxy import get_active_proxy_config

logger = logging.getLogger(__name__)


def _browser_proxy_server(purl: str) -> str:
    """Adapt an egress proxy URL to what Chromium's --proxy-server accepts.

    Chromium understands ``socks5://host:port`` (and resolves DNS through the
    SOCKS proxy) but not the ``socks5h://`` scheme we use for httpx/Tor, so
    translate the scheme for the browser. HTTP proxies (gluetun) pass through
    unchanged. Note: Chromium cannot do *authenticated* SOCKS5 — our gluetun
    path is HTTP and Tor is unauthenticated SOCKS5, so both are fine.
    """
    if purl.startswith("socks5h://"):
        return "socks5://" + purl[len("socks5h://"):]
    return purl


def _make_run_cfg(timeout_ms: int = 30000, proxy: Crawl4aiProxyConfig | None = None) -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=50,
        page_timeout=timeout_ms,
        proxy_config=proxy,
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

    # Resolve the active collection-egress proxy (fail-safe to direct) and
    # build the browser + run config PER CRAWL so a proxy-mode change takes
    # effect immediately (no module-level singleton to go stale).
    cfg = await get_active_proxy_config()
    purl = cfg.get_proxy_url()
    crawl_proxy = Crawl4aiProxyConfig(server=_browser_proxy_server(purl)) if purl else None

    browser_cfg = BrowserConfig(
        headless=True,
        browser_type="chromium",
        proxy_config=crawl_proxy,
        extra_args=["--dns-prefetch-disable"] if purl else [],
    )
    run_cfg = _make_run_cfg(timeout_ms, crawl_proxy)
    documents = []

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
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
