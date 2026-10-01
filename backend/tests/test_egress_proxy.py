"""The browser's egress proxy, run for real on local sockets.

Every test starts the actual proxy on 127.0.0.1, talks to it over a real
socket, and (where a request is allowed) reaches a real local server. There is
no external network: the resolver is faked at `url_guard._getaddrinfo`, the
one lookup the SSRF guard makes, and a public address the proxy vetted is
mapped onto a local server by the proxy's socket seam, which records the
address it was asked to dial.

Review focus 2: a host whose first resolution is public and second is private.
The proxy must connect to the address it vetted and never resolve again.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket

import pytest

from intel_platform.collection import url_guard
from intel_platform.collection.egress_proxy import EgressProxy, Upstream

PUBLIC = "93.184.216.34"


# ---------------------------------------------------------------------------
# Local servers
# ---------------------------------------------------------------------------

class _Server:
    """A local TCP server whose per-connection behaviour is a coroutine."""

    def __init__(self, behaviour):
        self._behaviour = behaviour
        self.connections = 0
        self.port = None
        self._server = None

    async def _handle(self, reader, writer):
        self.connections += 1
        try:
            await self._behaviour(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def __aenter__(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self._server.close()


async def _echo(reader, writer):
    while data := await reader.read(4096):
        writer.write(data)
        await writer.drain()


def _http_origin(seen: list):
    async def origin(reader, writer):
        seen.append((await reader.readuntil(b"\r\n\r\n")).decode("latin-1"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        await writer.drain()
    return origin


def _socks5_upstream(seen: list):
    """A SOCKS5 server (no auth) that records the requested address, then echoes."""
    async def socks(reader, writer):
        _ver, n = await reader.readexactly(2)
        await reader.readexactly(n)
        writer.write(b"\x05\x00")
        _ver, _cmd, _rsv, atyp = await reader.readexactly(4)
        if atyp == 3:
            host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
        else:
            host = str(ipaddress.ip_address(await reader.readexactly(4 if atyp == 1 else 16)))
        port = int.from_bytes(await reader.readexactly(2), "big")
        seen.append((atyp, host, port))
        writer.write(b"\x05\x00\x00\x01" + bytes(4) + b"\x00\x00")
        await writer.drain()
        await _echo(reader, writer)
    return socks


def _http_upstream(seen: list):
    """An HTTP proxy that records each request head; CONNECT then echoes."""
    async def proxy(reader, writer):
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        seen.append(head)
        if head.startswith("CONNECT "):
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await _echo(reader, writer)
        else:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: close\r\n\r\nvpn")
            await writer.drain()
    return proxy


# ---------------------------------------------------------------------------
# Resolver and socket seams
# ---------------------------------------------------------------------------

@pytest.fixture
def resolver(monkeypatch):
    """`url_guard._getaddrinfo`, answering from a script and recording every lookup."""
    state = type("Resolver", (), {})()
    state.lookups = []
    state.answers = {}

    def fake(host):
        state.lookups.append(host)
        script = state.answers.get(host)
        if script is None:
            raise socket.gaierror(f"no answer scripted for {host}")
        ips = script.pop(0) if isinstance(script[0], list) else script
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]

    monkeypatch.setattr(url_guard, "_getaddrinfo", fake)
    return state


def _dialer(route_to_port: int, dialed: list):
    """The proxy's socket seam: records the address dialled, connects locally."""
    async def open_connection(host, port):
        ipaddress.ip_address(host)  # only ever a vetted address, never a name
        dialed.append((host, port))
        return await asyncio.open_connection("127.0.0.1", route_to_port)
    return open_connection


async def _connect(proxy: EgressProxy, target: str):
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    await writer.drain()
    head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    return reader, writer, int(head.split(b" ")[1])


async def _request(proxy: EgressProxy, raw: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(raw)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return data


async def _roundtrip(reader, writer, payload=b"ping"):
    writer.write(payload)
    await writer.drain()
    return await asyncio.wait_for(reader.readexactly(len(payload)), 5)


# ---------------------------------------------------------------------------
# Direct: resolve once, vet, connect to what was vetted
# ---------------------------------------------------------------------------

class TestRebinding:
    """Review focus 2."""

    async def test_it_connects_to_the_vetted_answer_and_never_re_resolves(self, resolver):
        resolver.answers["rebind.example.com"] = [[PUBLIC], ["127.0.0.1"]]
        dialed: list = []
        async with _Server(_echo) as origin, EgressProxy(open_connection=_dialer(origin.port, dialed)) as proxy:
            reader, writer, status = await _connect(proxy, "rebind.example.com:443")
            assert status == 200
            assert await _roundtrip(reader, writer) == b"ping"
            writer.close()
            assert resolver.lookups == ["rebind.example.com"], "resolved more than once"
            assert dialed == [(PUBLIC, 443)], "connected somewhere other than the vetted address"

            # The next connection resolves afresh, gets the private answer, and is refused.
            _r, w2, status = await _connect(proxy, "rebind.example.com:443")
            w2.close()
            assert status == 403
            assert dialed == [(PUBLIC, 443)]
            assert proxy.refused and "rebind.example.com" in proxy.refused[-1][0]

    async def test_every_answer_must_be_public(self, resolver):
        resolver.answers["mixed.example.com"] = [PUBLIC, "10.0.0.7"]
        dialed: list = []
        async with EgressProxy(open_connection=_dialer(1, dialed)) as proxy:
            _r, w, status = await _connect(proxy, "mixed.example.com:443")
            w.close()
        assert status == 403 and dialed == []

    async def test_a_lookup_failure_is_refused_not_passed_through(self, resolver):
        dialed: list = []
        async with EgressProxy(open_connection=_dialer(1, dialed)) as proxy:
            _r, w, status = await _connect(proxy, "unresolvable.example.com:443")
            w.close()
        assert status == 403 and dialed == []

    async def test_the_next_vetted_address_is_tried_when_one_is_down(self, resolver):
        resolver.answers["two.example.com"] = [PUBLIC, "93.184.216.35"]
        dialed: list = []

        async with _Server(_echo) as origin:
            async def flaky(host, port):
                dialed.append((host, port))
                if host == PUBLIC:
                    raise ConnectionRefusedError()
                return await asyncio.open_connection("127.0.0.1", origin.port)

            async with EgressProxy(open_connection=flaky) as proxy:
                reader, writer, status = await _connect(proxy, "two.example.com:443")
                assert status == 200 and await _roundtrip(reader, writer) == b"ping"
                writer.close()
        assert dialed == [(PUBLIC, 443), ("93.184.216.35", 443)]
        assert resolver.lookups == ["two.example.com"]


class TestInternalTargetsAreRefused:
    @pytest.mark.parametrize("target", [
        "127.0.0.1:8000", "localhost:80", "[::1]:443", "169.254.169.254:80",
        "10.1.2.3:443", "postgres:5432", "0x7f.1:80", "host.docker.internal:8000",
    ])
    async def test_connect(self, resolver, target):
        dialed: list = []
        async with EgressProxy(open_connection=_dialer(1, dialed)) as proxy:
            _r, w, status = await _connect(proxy, target)
            w.close()
        assert status == 403 and dialed == []

    async def test_plain_http(self, resolver):
        dialed: list = []
        async with EgressProxy(open_connection=_dialer(1, dialed)) as proxy:
            reply = await _request(proxy, b"GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\n"
                                          b"Host: 169.254.169.254\r\n\r\n")
        assert reply.startswith(b"HTTP/1.1 403") and dialed == []


class TestPlainHttp:
    async def test_it_is_sent_to_the_vetted_origin_in_origin_form(self, resolver):
        resolver.answers["news.example.org"] = [PUBLIC]
        seen: list = []
        dialed: list = []
        async with _Server(_http_origin(seen)) as origin, \
                EgressProxy(open_connection=_dialer(origin.port, dialed)) as proxy:
            reply = await _request(
                proxy,
                b"GET http://news.example.org/story?id=7 HTTP/1.1\r\nHost: news.example.org\r\n"
                b"Proxy-Connection: keep-alive\r\nProxy-Authorization: Basic eDp5\r\nAccept: */*\r\n\r\n",
            )
        assert reply.endswith(b"hello")
        assert dialed == [(PUBLIC, 80)]
        [head] = seen
        assert head.startswith("GET /story?id=7 HTTP/1.1\r\n")
        assert "Host: news.example.org" in head and "Accept: */*" in head
        assert "Proxy-" not in head, "hop-by-hop proxy headers must not reach the origin"
        assert "Connection: close" in head

    async def test_an_https_url_in_absolute_form_is_not_forwarded(self, resolver):
        async with EgressProxy(open_connection=_dialer(1, [])) as proxy:
            reply = await _request(proxy, b"GET https://news.example.org/ HTTP/1.1\r\nHost: x\r\n\r\n")
        assert reply.startswith(b"HTTP/1.1 400")


# ---------------------------------------------------------------------------
# Chained: Tor and VPN are handed the hostname, never resolved here
# ---------------------------------------------------------------------------

class TestChainedUpstreams:
    async def test_tor_gets_the_hostname_and_nothing_is_resolved_locally(self, resolver):
        seen: list = []
        async with _Server(_socks5_upstream(seen)) as tor, \
                EgressProxy(upstream=f"socks5h://127.0.0.1:{tor.port}") as proxy:
            reader, writer, status = await _connect(proxy, "news.example.org:443")
            assert status == 200 and await _roundtrip(reader, writer) == b"ping"
            writer.close()
        assert seen == [(3, "news.example.org", 443)], "the far end must resolve the name"
        assert resolver.lookups == [], "Tor mode leaked the hostname to the local resolver"

    async def test_the_vpn_proxy_gets_a_connect_for_the_hostname(self, resolver):
        seen: list = []
        async with _Server(_http_upstream(seen)) as vpn, \
                EgressProxy(upstream=f"http://127.0.0.1:{vpn.port}") as proxy:
            reader, writer, status = await _connect(proxy, "news.example.org:443")
            assert status == 200 and await _roundtrip(reader, writer) == b"ping"
            writer.close()
        assert seen[0].startswith("CONNECT news.example.org:443 HTTP/1.1")
        assert resolver.lookups == []

    async def test_plain_http_through_the_vpn_keeps_the_absolute_form(self, resolver):
        seen: list = []
        async with _Server(_http_upstream(seen)) as vpn, \
                EgressProxy(upstream=f"http://user:p%40ss@127.0.0.1:{vpn.port}") as proxy:
            reply = await _request(proxy, b"GET http://news.example.org/a HTTP/1.1\r\nHost: news.example.org\r\n\r\n")
        assert reply.endswith(b"vpn")
        assert seen[0].startswith("GET http://news.example.org/a HTTP/1.1")
        assert "Proxy-Authorization: Basic dXNlcjpwQHNz" in seen[0]
        assert resolver.lookups == []

    async def test_internal_targets_are_still_refused_and_never_reach_the_upstream(self, resolver):
        seen: list = []
        async with _Server(_socks5_upstream(seen)) as tor, \
                EgressProxy(upstream=f"socks5h://127.0.0.1:{tor.port}") as proxy:
            for target in ("127.0.0.1:8000", "localhost:80", "neo4j:7687"):
                _r, w, status = await _connect(proxy, target)
                w.close()
                assert status == 403, target
            assert tor.connections == 0
        assert resolver.lookups == []

    async def test_an_unreachable_upstream_fails_closed(self, resolver):
        """Never fall back to direct when Tor or the VPN was chosen."""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            dead_port = s.getsockname()[1]
        async with EgressProxy(upstream=f"socks5h://127.0.0.1:{dead_port}", connect_timeout=2) as proxy:
            _r, w, status = await _connect(proxy, "news.example.org:443")
            w.close()
        assert status == 502
        assert resolver.lookups == []

    def test_upstream_urls(self):
        assert Upstream.parse("socks5h://tor:9050") == Upstream("socks5", "tor", 9050)
        assert Upstream.parse("socks5://127.0.0.1:1080").kind == "socks5"
        assert Upstream.parse("http://gluetun:8888") == Upstream("http", "gluetun", 8888)
        with pytest.raises(ValueError):
            Upstream.parse("https://proxy.example:443")


# ---------------------------------------------------------------------------
# The proxy itself
# ---------------------------------------------------------------------------

class TestTheListener:
    async def test_it_listens_on_loopback_only_and_stops_with_its_crawl(self):
        proxy = await EgressProxy().start()
        assert proxy.url == f"http://127.0.0.1:{proxy.port}"
        await proxy.close()
        with pytest.raises(OSError):
            _r, w = await asyncio.open_connection("127.0.0.1", proxy.port)
            w.close()

    async def test_malformed_requests_are_400(self):
        async with EgressProxy() as proxy:
            assert (await _request(proxy, b"NONSENSE\r\n\r\n")).startswith(b"HTTP/1.1 400")
            assert (await _request(proxy, b"CONNECT nohostport HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 400")

    async def test_an_oversized_head_is_refused(self):
        async with EgressProxy() as proxy:
            reply = await _request(proxy, b"GET http://a.example/ HTTP/1.1\r\nX: " + b"a" * 70000 + b"\r\n\r\n")
        assert reply.startswith(b"HTTP/1.1 431")

    async def test_closing_ends_open_tunnels(self, resolver):
        resolver.answers["news.example.org"] = [PUBLIC]
        async with _Server(_echo) as origin:
            proxy = await EgressProxy(open_connection=_dialer(origin.port, [])).start()
            reader, writer, status = await _connect(proxy, "news.example.org:443")
            assert status == 200
            await asyncio.wait_for(proxy.close(), 5)
            assert await asyncio.wait_for(reader.read(), 5) == b""
            writer.close()


# ---------------------------------------------------------------------------
# The crawler hands it to Chromium
# ---------------------------------------------------------------------------

def _capturing_crawler(seen: dict, during):
    """An AsyncWebCrawler stand-in that records its BrowserConfig and runs
    `during()` while the crawl is in progress."""
    from types import SimpleNamespace

    class FakeCrawler:
        def __init__(self, config=None, **kwargs):
            seen["browser"] = config
            self.crawler_strategy = SimpleNamespace(set_hook=lambda name, fn: seen.setdefault("hooks", {}).update({name: fn}))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def arun_many(self, urls, config=None):
            seen["run"] = config
            await during()
            return [SimpleNamespace(
                success=True, url=u, redirected_url=None, error_message=None,
                markdown=SimpleNamespace(raw_markdown="Body text " * 20, fit_markdown="Body text " * 20),
                metadata={"title": "T"}, links={},
            ) for u in urls]

    return FakeCrawler


def _mode(monkeypatch, mode: str):
    from intel_platform.collection import crawler as crawler_mod
    from intel_platform.collection.proxy import ProxyConfig

    async def active():
        return ProxyConfig(mode=mode)

    monkeypatch.setattr(crawler_mod, "get_active_proxy_config", active)
    monkeypatch.setattr("intel_platform.collection.proxy.settings.tor_socks_proxy", "socks5h://tor:9050")
    monkeypatch.setattr("intel_platform.collection.proxy.settings.vpn_http_proxy", "http://gluetun:8888")
    return crawler_mod


class TestTheCrawlerUsesIt:
    async def test_chromium_is_pointed_at_a_live_enforcing_proxy(self, monkeypatch, resolver):
        crawler_mod = _mode(monkeypatch, "direct")
        resolver.answers["news.example.org"] = [PUBLIC]
        seen: dict = {}

        async def during():
            server = seen["browser"].proxy_config.server
            assert server.startswith("http://127.0.0.1:")
            port = int(server.rsplit(":", 1)[1])
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"CONNECT 169.254.169.254:80 HTTP/1.1\r\n\r\n")
            await writer.drain()
            seen["refusal"] = await asyncio.wait_for(reader.readuntil(b"\r\n"), 5)
            writer.close()
            seen["port"] = port

        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _capturing_crawler(seen, during))
        docs = await crawler_mod.crawl_urls(["https://news.example.org/story"])

        assert len(docs) == 1
        assert seen["refusal"].startswith(b"HTTP/1.1 403")
        assert seen["run"].proxy_config.server == seen["browser"].proxy_config.server
        args = seen["browser"].extra_args
        assert "--proxy-bypass-list=<-loopback>" in args and "--dns-prefetch-disable" in args
        # The proxy lives only as long as the crawl.
        with pytest.raises(OSError):
            _r, w = await asyncio.open_connection("127.0.0.1", seen["port"])
            w.close()

    async def test_the_connected_address_check_gives_way_to_the_proxy(self, monkeypatch, resolver):
        """Behind the egress proxy every response comes from 127.0.0.1, so the
        in-browser address check would reject every page; the proxy pins instead."""
        crawler_mod = _mode(monkeypatch, "direct")
        resolver.answers["news.example.org"] = [PUBLIC]
        made = []
        real_guard = crawler_mod._BrowserGuard

        def guard(**kw):
            made.append(kw)
            return real_guard(**kw)

        monkeypatch.setattr(crawler_mod, "_BrowserGuard", guard)
        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _capturing_crawler({}, _nothing))
        await crawler_mod.crawl_urls(["https://news.example.org/story"])
        assert made == [{"direct": True, "check_address": False}]

    @pytest.mark.parametrize("mode,upstream", [
        ("tor", Upstream("socks5", "tor", 9050)),
        ("vpn", Upstream("http", "gluetun", 8888)),
    ])
    async def test_tor_and_vpn_are_chained_behind_it(self, monkeypatch, resolver, mode, upstream):
        crawler_mod = _mode(monkeypatch, mode)
        seen: dict = {}
        started = []

        class Recording(EgressProxy):
            async def start(self):
                started.append(self.upstream)
                return await super().start()

        monkeypatch.setattr(crawler_mod, "EgressProxy", Recording)
        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _capturing_crawler(seen, _nothing))
        await crawler_mod.crawl_urls(["https://news.example.org/story"])

        assert started == [upstream]
        assert seen["browser"].proxy_config.server.startswith("http://127.0.0.1:"), \
            "the browser must talk to the local proxy, not to Tor/VPN directly"
        assert resolver.lookups == [], "no local lookups behind Tor/VPN"

    async def test_disabled_it_is_the_previous_behaviour(self, monkeypatch, resolver):
        crawler_mod = _mode(monkeypatch, "tor")
        monkeypatch.setattr(crawler_mod, "_egress_proxy_enabled", lambda: False)
        seen: dict = {}
        monkeypatch.setattr(crawler_mod, "AsyncWebCrawler", _capturing_crawler(seen, _nothing))
        await crawler_mod.crawl_urls(["https://news.example.org/story"])
        assert seen["browser"].proxy_config.server == "socks5://tor:9050"

    def test_the_setting_defaults_on(self, monkeypatch):
        from types import SimpleNamespace

        from intel_platform.collection import crawler as crawler_mod

        monkeypatch.setattr(crawler_mod, "settings", SimpleNamespace())
        assert crawler_mod._egress_proxy_enabled() is True
        monkeypatch.setattr(crawler_mod, "settings", SimpleNamespace(egress_proxy_enabled=False))
        assert crawler_mod._egress_proxy_enabled() is False


async def _nothing():
    return None
