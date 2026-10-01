from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from urllib.parse import urlsplit

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai import ProxyConfig as Crawl4aiProxyConfig

from intel_platform.collection.egress_proxy import EgressProxy
from intel_platform.collection.proxy import get_active_proxy_config
from intel_platform.collection.url_guard import _is_private_ip, is_safe_url_async
from intel_platform.config import settings

logger = logging.getLogger(__name__)

# Chromium flags whenever its traffic goes through a proxy.
_PROXIED_BROWSER_ARGS = [
    "--dns-prefetch-disable",
    # Chromium sends loopback straight out, bypassing any proxy, unless told
    # otherwise; through the proxy it is refused like any internal target.
    "--proxy-bypass-list=<-loopback>",
    # Neither QUIC nor WebRTC's UDP goes through an HTTP proxy.
    "--disable-quic",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
]


def _egress_proxy_enabled() -> bool:
    """settings.egress_proxy_enabled (default True): route Chromium through EgressProxy."""
    return bool(getattr(settings, "egress_proxy_enabled", True))

# Rejection reasons reported for a crawled page the guard refused to keep.
REDIRECT_UNSAFE = "redirect_unsafe"
INTERNAL_ADDRESS = "internal_address"

# Schemes a page can load without touching the network.
_LOCAL_SCHEMES = ("data:", "blob:", "about:")


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


def _is_internal_address(ip: str) -> bool:
    """The guard's own rule, applied to the address Chromium connected to."""
    return _is_private_ip(ip)


class _BrowserGuard:
    """SSRF enforcement inside the headless browser, for one crawl.

    The URL list is vetted before the browser starts, but that vets only the
    first request. Chromium then follows 3xx redirects, runs page JavaScript
    that navigates or fetches, and loads subresources, none of which the
    pre-filter sees. A public page answering ``302 Location:
    http://169.254.169.254/...`` was stored as a Document holding the metadata
    service's response. Three checks cover what the pre-filter cannot:

    * Every request the browser routes is vetted and aborted if unsafe: JS
      navigations, fetch/XHR, subresources, and the first hop of a navigation;
      the context is routed too (service-worker fetches bypass page routes),
      and WebSockets are vetted and closed if unsafe.
    * Redirect hops, which Playwright does **not** route (its handler sees only
      the first URL of a redirect chain), are recorded from the request events,
      and a page is rejected if any hop was unsafe. A public → internal →
      public chain ends on a safe-looking URL, so the final URL alone is not
      enough.
    * In direct mode without the egress proxy, the address Chromium actually
      connected to is checked for every response. A rebinding hostname can give
      the guard's lookup and the browser's different answers; the connected
      socket cannot. Behind any proxy that address is the proxy's, so the check
      is skipped there.

    On its own this cannot stop the browser *sending* a redirected request to
    an internal host, or a rebinding name answering the route check with a
    public address and Chromium's own lookup with an internal one. That is what
    ``egress_proxy.EgressProxy`` closes (on by default): Chromium's every
    connection goes through it, and it connects only to the address it vetted.
    """

    def __init__(self, *, direct: bool, check_address: bool | None = None):
        self._direct = direct
        self._address_checked = direct if check_address is None else check_address
        self._verdicts: dict[str, bool] = {}
        self._start_url: dict[Any, str] = {}
        self._hops: list[tuple[Any, str]] = []
        self._internal: dict[Any, str] = {}
        self._pending: dict[Any, list[asyncio.Future]] = {}
        self._routed_contexts: set = set()

    def install(self, crawler) -> None:
        """Register the hooks, or refuse to crawl without them."""
        strategy = getattr(crawler, "crawler_strategy", None)
        set_hook = getattr(strategy, "set_hook", None)
        if set_hook is None:
            raise RuntimeError("crawl4ai exposes no hooks; refusing to crawl without the in-browser SSRF guard")
        set_hook("on_page_context_created", self.on_page_context_created)
        set_hook("before_goto", self.before_goto)
        set_hook("before_retrieve_html", self.before_retrieve_html)

    async def is_safe(self, url: str) -> bool:
        if url.startswith(_LOCAL_SCHEMES):
            return True
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key not in self._verdicts:
            self._verdicts[key] = await is_safe_url_async(url, resolve=self._direct)
        return self._verdicts[key]

    # -- crawl4ai hooks -------------------------------------------------------

    async def on_page_context_created(self, page, context=None, **kwargs):
        await page.route("**/*", self._route)
        # Service-worker fetches bypass page routes; the context's route sees
        # them. A context can hold several pages, so it is routed once.
        if context is not None and context not in self._routed_contexts:
            self._routed_contexts.add(context)
            await context.route("**/*", self._route)
        # WebSockets are not routed by page.route at all.
        route_web_socket = getattr(page, "route_web_socket", None)
        if route_web_socket is not None:
            await route_web_socket("**/*", self._route_ws)
        page.on("request", lambda request: self._on_request(page, request))
        if self._address_checked:
            page.on("response", lambda response: self._on_response(page, response))
        return page

    async def before_goto(self, page, context=None, url: str = "", **kwargs):
        self._start_url[page] = url
        return page

    async def before_retrieve_html(self, page, context=None, **kwargs):
        # Settle this page's address checks before its content is read.
        pending = self._pending.pop(page, [])
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return page

    # -- Playwright handlers --------------------------------------------------

    async def _route(self, route) -> None:
        url = route.request.url
        if await self.is_safe(url):
            await route.continue_()
            return
        logger.warning("Browser request blocked by SSRF guard: %s", url[:200])
        await route.abort("blockedbyclient")

    async def _route_ws(self, ws) -> None:
        url = ws.url
        # ws:// and wss:// are vetted as the http(s) origin they upgrade from.
        http_url = "http" + url[2:] if url.startswith("ws") else url
        if await self.is_safe(http_url):
            ws.connect_to_server()
            return
        logger.warning("Browser WebSocket blocked by SSRF guard: %s", url[:200])
        await ws.close(code=1008, reason="blocked")

    def _on_request(self, page, request) -> None:
        if getattr(request, "redirected_from", None) is not None:
            self._hops.append((page, request.url))

    def _on_response(self, page, response) -> None:
        task = asyncio.ensure_future(self._check_address(page, response))
        self._pending.setdefault(page, []).append(task)

    async def _check_address(self, page, response) -> None:
        try:
            addr = await response.server_addr()
        except Exception:
            logger.debug("Could not read the server address for %s", getattr(response, "url", "?"), exc_info=True)
            return
        ip = addr.get("ipAddress") if isinstance(addr, dict) else None
        if ip and _is_internal_address(ip):
            self._internal.setdefault(page, f"{getattr(response, 'url', '?')} via {ip}")

    # -- verdicts -------------------------------------------------------------

    async def rejections(self) -> dict[str, str]:
        """Requested URL -> reason, for every page the guard refuses to keep."""
        pending = [t for tasks in self._pending.values() for t in tasks]
        self._pending.clear()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        out: dict[str, str] = {}
        for page, hop in self._hops:
            start = self._start_url.get(page)
            if start and start not in out and not await self.is_safe(hop):
                logger.warning("Crawl of %s redirected through an unsafe URL: %s", start[:200], hop[:200])
                out[start] = REDIRECT_UNSAFE
        for page, detail in self._internal.items():
            start = self._start_url.get(page)
            if start and start not in out:
                logger.warning("Crawl of %s was served from an internal address: %s", start[:200], detail[:200])
                out[start] = INTERNAL_ADDRESS
        return out


async def crawl_urls(
    urls: list[str],
    timeout_ms: int = 30000,
    on_progress: Callable[[str, str], None] | None = None,
    rejected: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """Crawl a list of URLs with headless Chromium and return structured documents.

    With ``egress_proxy_enabled`` (the default) the browser's only route out is
    a local ``EgressProxy`` started for this crawl: in direct mode it connects
    only to addresses the SSRF guard vetted, and with Tor or the VPN selected it
    chains to that proxy without resolving anything locally.

    Args:
        urls: URLs to crawl.
        timeout_ms: Per-page timeout in milliseconds.
        on_progress: Optional callback(url, status) for progress tracking.
        rejected: Optional list that receives ``(url, reason)`` for every page
            fetched but refused by the SSRF guard, so a caller can report it
            rather than see an unexplained missing document.

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
    direct = not purl

    # SSRF guard: validate EVERY URL here so no fetch path can bypass it (the
    # runner and agentic paths call crawl_urls directly, not via WebScraper).
    # Drop unsafe URLs rather than fail the whole batch. Behind a proxy the
    # target resolves at the far end, so it is not looked up locally (that
    # leaked every hostname to the local resolver in Tor mode).
    safe_urls: list[str] = []
    for u in urls:
        if await is_safe_url_async(u, resolve=direct):
            safe_urls.append(u)
        else:
            logger.warning("Skipping unsafe URL (SSRF guard): %s", u)
    urls = safe_urls
    if not urls:
        return []

    if _egress_proxy_enabled():
        try:
            egress = EgressProxy(upstream=purl)
        except ValueError:
            # An upstream scheme the egress proxy cannot chain to: hand it to
            # Chromium directly, as before the egress proxy existed.
            logger.warning("Egress proxy cannot chain to %s; the browser connects to it directly", purl)
        else:
            async with egress:
                # The browser's connected address is now the egress proxy's,
                # which pins and vets every target itself.
                return await _crawl(
                    urls, timeout_ms, on_progress, rejected,
                    browser_proxy=egress.url, guard=_BrowserGuard(direct=direct, check_address=False),
                )
    return await _crawl(
        urls, timeout_ms, on_progress, rejected,
        browser_proxy=_browser_proxy_server(purl) if purl else None, guard=_BrowserGuard(direct=direct),
    )


async def _crawl(urls, timeout_ms, on_progress, rejected, *, browser_proxy: str | None, guard: _BrowserGuard):
    """Run the browser over `urls` (already vetted), through `browser_proxy` if set."""
    crawl_proxy = Crawl4aiProxyConfig(server=browser_proxy) if browser_proxy else None

    browser_cfg = BrowserConfig(
        headless=True,
        browser_type="chromium",
        # Becomes Chromium's --proxy-server.
        proxy_config=crawl_proxy,
        extra_args=list(_PROXIED_BROWSER_ARGS) if browser_proxy else [],
    )
    run_cfg = _make_run_cfg(timeout_ms, crawl_proxy)
    documents = []

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        guard.install(crawler)
        results = await crawler.arun_many(urls=urls, config=run_cfg)
        refused = await guard.rejections()

        for result in results:
            if not result.success:
                logger.warning("Crawl failed for %s: %s", result.url, result.error_message)
                if on_progress:
                    on_progress(result.url, "error")
                continue

            # Where the page ended up, after 3xx and JS navigation.
            final_url = result.redirected_url if isinstance(result.redirected_url, str) else ""
            reason = refused.get(result.url)
            if reason is None and final_url and not await guard.is_safe(final_url):
                logger.warning("Crawl of %s ended on an unsafe URL: %s", result.url, final_url[:200])
                reason = REDIRECT_UNSAFE
            if reason is not None:
                if rejected is not None:
                    rejected.append((result.url, reason))
                if on_progress:
                    on_progress(result.url, "rejected")
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
