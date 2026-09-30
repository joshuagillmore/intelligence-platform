"""The headless browser must not carry a crawl onto an internal host.

The URL list is vetted before the browser starts, but that only vets the first
request. Chromium follows 3xx redirects and runs page JavaScript that navigates,
so a public page answering ``302 Location: http://169.254.169.254/...`` used to
be stored as a Document holding the metadata service's response.

Everything here is a fake: no browser, no DNS, no network. Hosts are IP
literals (which resolve to themselves without a lookup) or blocklisted names.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intel_platform.collection import crawler as crawler_mod
from intel_platform.collection.proxy import ProxyConfig

PUBLIC_START = "https://93.184.216.34/start"
PUBLIC_FINAL = "https://93.184.216.35/landing"
METADATA = "http://169.254.169.254/latest/meta-data/"
LOOPBACK_API = "http://127.0.0.1:8000/api/projects"


# ---------------------------------------------------------------------------
# Fakes for crawl4ai and Playwright
# ---------------------------------------------------------------------------

class FakeRequest:
    def __init__(self, url, redirected_from=None):
        self.url = url
        self.redirected_from = redirected_from


class FakeRoute:
    def __init__(self, url):
        self.request = FakeRequest(url)
        self.outcome = None

    async def continue_(self, **kwargs):
        self.outcome = "continue"

    async def abort(self, error_code=None):
        self.outcome = "abort"


class FakeResponse:
    def __init__(self, url, ip):
        self.url = url
        self._ip = ip

    async def server_addr(self):
        return {"ipAddress": self._ip, "port": 443}


class FakePage:
    """Records the route handler and event listeners the guard installs."""

    def __init__(self):
        self.route_handler = None
        self.listeners: dict[str, list] = {}

    async def route(self, pattern, handler):
        self.route_handler = handler

    def on(self, event, fn):
        self.listeners.setdefault(event, []).append(fn)

    def emit(self, event, payload):
        for fn in self.listeners.get(event, []):
            fn(payload)


class FakeStrategy:
    def __init__(self):
        self.hooks: dict = {}

    def set_hook(self, name, fn):
        self.hooks[name] = fn


def _result(url, redirected_url=None, content="Some real article text about the subject."):
    return SimpleNamespace(
        success=True,
        url=url,
        redirected_url=redirected_url,
        markdown=SimpleNamespace(raw_markdown=content, fit_markdown=content),
        metadata={"title": "T"},
        links={"internal": [], "external": []},
        error_message=None,
    )


def _fake_crawler(scenario):
    """An AsyncWebCrawler stand-in whose arun_many runs `scenario(hooks, urls)`."""

    class FakeCrawler:
        def __init__(self, config=None, **kwargs):
            self.crawler_strategy = FakeStrategy()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def arun_many(self, urls, config=None):
            return await scenario(self.crawler_strategy.hooks, list(urls))

    return FakeCrawler


async def _open_page(hooks, url):
    """Drive the hooks the way crawl4ai does for one page."""
    page = FakePage()
    await hooks["on_page_context_created"](page, context=None, config=None)
    await hooks["before_goto"](page, context=None, url=url, config=None)
    return page


@pytest.fixture
def direct_mode(monkeypatch):
    async def _direct():
        return ProxyConfig(mode="direct")

    monkeypatch.setattr(crawler_mod, "get_active_proxy_config", _direct)


# ---------------------------------------------------------------------------
# The final URL
# ---------------------------------------------------------------------------

class TestFinalUrlIsChecked:
    async def test_result_redirected_to_metadata_service_is_dropped(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            return [_result(PUBLIC_START, redirected_url=METADATA)]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        rejected: list = []
        docs = await crawler_mod.crawl_urls([PUBLIC_START], rejected=rejected)

        assert docs == [], "an internal response must never become a Document"
        assert rejected == [(PUBLIC_START, "redirect_unsafe")]

    async def test_result_redirected_to_another_public_host_is_kept(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            return [_result(PUBLIC_START, redirected_url=PUBLIC_FINAL)]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        rejected: list = []
        docs = await crawler_mod.crawl_urls([PUBLIC_START], rejected=rejected)

        assert len(docs) == 1 and rejected == []

    async def test_progress_callback_hears_about_the_rejection(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            return [_result(PUBLIC_START, redirected_url=LOOPBACK_API)]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        seen = []
        await crawler_mod.crawl_urls([PUBLIC_START], on_progress=lambda u, s: seen.append((u, s)))
        assert seen == [(PUBLIC_START, "rejected")]


# ---------------------------------------------------------------------------
# Requests the browser makes after the first one
# ---------------------------------------------------------------------------

class TestRequestsAreRoutedThroughTheGuard:
    async def test_unsafe_request_is_aborted_and_safe_one_continues(self, monkeypatch, direct_mode):
        routes = {}

        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            for url in (METADATA, LOOPBACK_API, PUBLIC_FINAL):
                route = FakeRoute(url)
                await page.route_handler(route)
                routes[url] = route.outcome
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        await crawler_mod.crawl_urls([PUBLIC_START])

        assert routes[METADATA] == "abort"
        assert routes[LOOPBACK_API] == "abort"
        assert routes[PUBLIC_FINAL] == "continue"

    async def test_internal_service_hostname_is_aborted(self, monkeypatch, direct_mode):
        outcome = {}

        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            route = FakeRoute("http://neo4j:7474/db/data/")
            await page.route_handler(route)
            outcome["neo4j"] = route.outcome
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        await crawler_mod.crawl_urls([PUBLIC_START])
        assert outcome["neo4j"] == "abort"


class FakeContext:
    def __init__(self):
        self.route_handler = None

    async def route(self, pattern, handler):
        self.route_handler = handler


class FakeWsRoute:
    def __init__(self, url):
        self.url = url
        self.outcome = None

    def connect_to_server(self):
        self.outcome = "connected"
        return self

    async def close(self, code=None, reason=None):
        self.outcome = "closed"


class TestRequestsOutsidePageRouting:
    """page.route sees neither service-worker fetches nor WebSockets, so a page
    could reach an internal host through either (found in review)."""

    async def test_service_worker_requests_are_routed_through_the_context(self, monkeypatch, direct_mode):
        seen = {}

        async def scenario(hooks, urls):
            page, context = FakePage(), FakeContext()
            await hooks["on_page_context_created"](page, context=context, config=None)
            await hooks["before_goto"](page, context=context, url=urls[0], config=None)
            route = FakeRoute(METADATA)
            await context.route_handler(route)
            seen["context"] = route.outcome
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        await crawler_mod.crawl_urls([PUBLIC_START])
        assert seen["context"] == "abort"

    async def test_websockets_to_internal_hosts_are_refused(self, monkeypatch, direct_mode):
        seen = {}

        class WsPage(FakePage):
            async def route_web_socket(self, pattern, handler):
                self.ws_handler = handler

        async def scenario(hooks, urls):
            page = WsPage()
            await hooks["on_page_context_created"](page, context=None, config=None)
            for url in ("ws://127.0.0.1:8000/socket", "wss://93.184.216.34/live"):
                ws = FakeWsRoute(url)
                await page.ws_handler(ws)
                seen[url] = ws.outcome
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        await crawler_mod.crawl_urls([PUBLIC_START])
        assert seen["ws://127.0.0.1:8000/socket"] == "closed"
        assert seen["wss://93.184.216.34/live"] == "connected"


class TestRedirectChains:
    """Playwright's route handler sees only the first URL of a redirect chain,
    so the hops are audited from the request events instead."""

    async def test_public_to_private_to_public_is_rejected(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            first = FakeRequest(urls[0])
            hop = FakeRequest(METADATA, redirected_from=first)
            final = FakeRequest(PUBLIC_FINAL, redirected_from=hop)
            for req in (first, hop, final):
                page.emit("request", req)
            # The final URL is public, so a final-URL check alone passes it.
            return [_result(urls[0], redirected_url=PUBLIC_FINAL)]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        rejected: list = []
        docs = await crawler_mod.crawl_urls([PUBLIC_START], rejected=rejected)

        assert docs == [], "a chain that passed through an internal host rejects the whole result"
        assert rejected == [(PUBLIC_START, "redirect_unsafe")]

    async def test_all_public_chain_is_kept(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            first = FakeRequest(urls[0])
            page.emit("request", first)
            page.emit("request", FakeRequest(PUBLIC_FINAL, redirected_from=first))
            return [_result(urls[0], redirected_url=PUBLIC_FINAL)]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        docs = await crawler_mod.crawl_urls([PUBLIC_START])
        assert len(docs) == 1

    async def test_rejection_is_per_page(self, monkeypatch, direct_mode):
        """One page's bad redirect must not take a clean page down with it."""
        other = "https://93.184.216.36/other"

        async def scenario(hooks, urls):
            bad = await _open_page(hooks, urls[0])
            await _open_page(hooks, urls[1])
            first = FakeRequest(urls[0])
            bad.emit("request", first)
            bad.emit("request", FakeRequest(LOOPBACK_API, redirected_from=first))
            return [_result(urls[0], redirected_url=LOOPBACK_API), _result(urls[1])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        docs = await crawler_mod.crawl_urls([PUBLIC_START, other])
        assert [d["url"] for d in docs] == [other]


class TestConnectedAddressIsEvidence:
    """A rebinding hostname passes any lookup the guard makes; the address the
    browser actually connected to is what it cannot disguise."""

    async def test_response_from_internal_address_rejects_the_page(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            page.emit("response", FakeResponse(urls[0], "10.0.0.7"))
            await hooks["before_retrieve_html"](page, context=None, config=None)
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        rejected: list = []
        docs = await crawler_mod.crawl_urls([PUBLIC_START], rejected=rejected)
        assert docs == []
        assert rejected == [(PUBLIC_START, "internal_address")]

    async def test_response_from_public_address_is_kept(self, monkeypatch, direct_mode):
        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            page.emit("response", FakeResponse(urls[0], "93.184.216.34"))
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        docs = await crawler_mod.crawl_urls([PUBLIC_START])
        assert len(docs) == 1


class TestProxyModeDoesNotResolveLocally:
    """In Tor mode the local resolver must never see the target hostname."""

    async def test_no_local_lookup_and_no_address_check(self, monkeypatch):
        from intel_platform.collection import url_guard

        lookups = []
        monkeypatch.setattr(url_guard, "_getaddrinfo", lambda host: lookups.append(host) or [])

        async def tor():
            return ProxyConfig(mode="tor")

        monkeypatch.setattr(crawler_mod, "get_active_proxy_config", tor)
        monkeypatch.setattr("intel_platform.collection.proxy.settings.tor_socks_proxy", "socks5h://tor:9050")

        async def scenario(hooks, urls):
            page = await _open_page(hooks, urls[0])
            route = FakeRoute("https://news.example.org/story")
            await page.route_handler(route)
            assert route.outcome == "continue"
            # The server address behind a proxy is the proxy's own, so it is
            # not evidence of anything and is not checked.
            assert "response" not in page.listeners
            return [_result(urls[0])]

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
        docs = await crawler_mod.crawl_urls(["https://news.example.org/"])
        assert len(docs) == 1
        assert lookups == []


async def test_scraper_surfaces_the_rejection_reason(monkeypatch, direct_mode):
    """A single-URL scrape that was rejected says why, not just 'failed'."""
    from intel_platform.collection.scraper import WebScraper

    async def scenario(hooks, urls):
        return [_result(PUBLIC_START, redirected_url=METADATA)]

    monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _fake_crawler(scenario))
    with pytest.raises(RuntimeError, match="redirect_unsafe"):
        await WebScraper().scrape_url(PUBLIC_START)
