import socket
from unittest.mock import patch

import httpcore
import pytest

from intel_platform.collection import proxy as proxy_mod
from intel_platform.collection import url_guard
from intel_platform.collection.proxy import ProxyConfig, get_active_proxy_config
from intel_platform.config import settings


def test_proxy_config_direct():
    config = ProxyConfig(mode="direct")
    assert config.get_client_kwargs() == {}


def test_proxy_config_tor():
    config = ProxyConfig(mode="tor", tor_port=9050)
    kwargs = config.get_client_kwargs()
    assert "proxy" in kwargs
    assert "9050" in kwargs["proxy"]


def test_proxy_config_proxy():
    config = ProxyConfig(mode="proxy", proxy_url="http://proxy:8080")
    kwargs = config.get_client_kwargs()
    assert kwargs["proxy"] == "http://proxy:8080"


# ---------------------------------------------------------------------------
# get_proxy_url() per mode
# ---------------------------------------------------------------------------

def test_get_proxy_url_direct_is_none():
    assert ProxyConfig(mode="direct").get_proxy_url() is None


def test_get_proxy_url_vpn_uses_settings():
    assert ProxyConfig(mode="vpn").get_proxy_url() == settings.vpn_http_proxy


def test_get_proxy_url_tor_uses_settings():
    assert ProxyConfig(mode="tor").get_proxy_url() == settings.tor_socks_proxy


def test_get_proxy_url_proxy_uses_explicit_url():
    assert ProxyConfig(mode="proxy", proxy_url="http://p:3128").get_proxy_url() == "http://p:3128"


# ---------------------------------------------------------------------------
# get_active_proxy_config() — DB-backed, fail-safe to direct
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._value)


def _fake_factory_returning(value):
    """Return a get_session_factory replacement whose session yields `value`."""
    return lambda: (lambda: _FakeSession(value))


async def test_get_active_proxy_config_defaults_direct_when_unset(monkeypatch):
    import intel_platform.db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_session_factory", _fake_factory_returning(None))
    cfg = await get_active_proxy_config()
    assert cfg.mode == "direct"
    assert cfg.get_proxy_url() is None


async def test_get_active_proxy_config_reads_stored_mode(monkeypatch):
    import intel_platform.db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_session_factory", _fake_factory_returning("vpn"))
    cfg = await get_active_proxy_config()
    assert cfg.mode == "vpn"
    assert cfg.get_proxy_url() == settings.vpn_http_proxy


async def test_get_active_proxy_config_unknown_mode_falls_back_direct(monkeypatch):
    import intel_platform.db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_session_factory", _fake_factory_returning("garbage"))
    cfg = await get_active_proxy_config()
    assert cfg.mode == "direct"


async def test_get_active_proxy_config_failsafe_on_db_error(monkeypatch):
    import intel_platform.db.engine as engine_mod

    def _boom():
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(engine_mod, "get_session_factory", _boom)
    cfg = await get_active_proxy_config()
    assert cfg.mode == "direct"
    assert cfg.get_client_kwargs() == {}


# ---------------------------------------------------------------------------
# LLM stays direct — never proxied, even with the collection proxy set to vpn
# ---------------------------------------------------------------------------

async def test_llm_provider_client_is_direct_even_with_vpn(monkeypatch):
    # Pin the collection proxy to vpn and spy on get_active_proxy_config so we
    # can prove the LLM path never consults it.
    import intel_platform.collection.proxy as proxy_mod

    called = {"v": False}

    async def _spy():
        called["v"] = True
        return proxy_mod.ProxyConfig(mode="vpn")

    monkeypatch.setattr(proxy_mod, "get_active_proxy_config", _spy)

    from intel_platform.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="test-key")
    # anthropic.AsyncAnthropic wraps an httpx.AsyncClient; an unproxied client
    # has NO transport mounts. A proxied one would have a proxy mount.
    httpx_client = provider._client._client
    assert httpx_client._mounts == {}, "LLM httpx client must be built with no proxy"
    assert called["v"] is False, "LLM path must never consult the collection proxy"


# ---------------------------------------------------------------------------
# web_search routes its egress through the passed proxy
# ---------------------------------------------------------------------------

def test_web_search_passes_proxy_to_ddgs():
    from intel_platform.collection.search import web_search

    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = []
        web_search("q", max_results=5, proxy="socks5h://tor:9050")

    # Search falls through to the next engine when one returns nothing, so DDGS
    # is constructed once per backend tried. Every one of them must carry the
    # proxy — a fallback engine that quietly bypassed the tunnel would leak the
    # collection's egress.
    assert MockDDGS.call_count >= 1
    assert {c.kwargs.get("proxy") for c in MockDDGS.call_args_list} == {"socks5h://tor:9050"}


def test_web_search_defaults_to_no_proxy():
    from intel_platform.collection.search import web_search

    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = []
        web_search("q", max_results=5)

    assert {c.kwargs.get("proxy") for c in MockDDGS.call_args_list} == {None}


# ---------------------------------------------------------------------------
# ProxiedClient.get/post forward params/json/headers and honor the proxy
# (Phase 2 — enrichment providers need GET params + POST)
# ---------------------------------------------------------------------------

class _CapturingClient:
    """Stand-in for httpx.AsyncClient that records how it was built and called."""
    captured: dict = {}

    def __init__(self, **kwargs):
        _CapturingClient.captured["init"] = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, **kwargs):
        # ProxiedClient streams every request so it can cap the body.
        _CapturingClient.captured["call"] = (method.lower(), url, kwargs)
        import contextlib

        import httpx

        @contextlib.asynccontextmanager
        async def _cm():
            yield httpx.Response(200, content=b"resp", request=httpx.Request(method, url))

        return _cm()


async def test_proxied_client_get_forwards_params_direct(monkeypatch):
    import intel_platform.collection.proxy as proxy_mod
    _CapturingClient.captured = {}
    monkeypatch.setattr(proxy_mod.httpx, "AsyncClient", _CapturingClient)

    client = proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="direct"))
    await client.get("http://x", headers={"H": "v"}, params={"q": "1"})

    method, url, kwargs = _CapturingClient.captured["call"]
    assert method == "get" and url == "http://x"
    assert kwargs["params"] == {"q": "1"}
    assert kwargs["headers"] == {"H": "v"}
    assert "proxy" not in _CapturingClient.captured["init"]  # direct -> unproxied


async def test_proxied_client_post_forwards_json_and_honors_vpn(monkeypatch):
    import intel_platform.collection.proxy as proxy_mod
    _CapturingClient.captured = {}
    monkeypatch.setattr(proxy_mod.httpx, "AsyncClient", _CapturingClient)

    client = proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="vpn"))
    await client.post("http://x", json={"a": 1}, headers={"H": "v"})

    method, url, kwargs = _CapturingClient.captured["call"]
    assert method == "post" and url == "http://x"
    assert kwargs["json"] == {"a": 1}
    # vpn mode -> the httpx client is built with the gluetun proxy
    assert _CapturingClient.captured["init"].get("proxy") == proxy_mod.settings.vpn_http_proxy


# ---------------------------------------------------------------------------
# Direct mode connects only to the address the guard vetted (C-5)
# ---------------------------------------------------------------------------
#
# The guard used to resolve a host, approve it, and hand the URL to httpx, which
# resolved it again. A TTL-0 rebinding name answers "public" to the first lookup
# and "127.0.0.1" to the second. Now the lookup happens once, at connect time,
# and the socket goes to exactly the address that was vetted.

class _SequencedDNS:
    """Answers each lookup of a host with the next address in its list."""

    def __init__(self, answers: dict[str, list[str]]):
        self.answers = {h: list(v) for h, v in answers.items()}
        self.calls: list[str] = []

    def __call__(self, host):
        self.calls.append(host)
        seq = self.answers.get(host)
        if not seq:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        ip = seq.pop(0) if len(seq) > 1 else seq[0]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    """Stands in for the socket layer: records where it was asked to connect."""

    def __init__(self, responses: dict[str, list[bytes]] | None = None):
        self.responses = responses or {}
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.connected.append((host, port))
        return httpcore.AsyncMockStream(list(self.responses.get(host, [])))

    async def sleep(self, seconds):
        return None


def _http(body: bytes, status: str = "200 OK", extra: str = "") -> list[bytes]:
    head = f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\n{extra}\r\n".encode()
    return [head, body]


@pytest.fixture
def fake_socket_layer(monkeypatch):
    backend = _RecordingBackend()
    monkeypatch.setattr(proxy_mod._PinnedBackend, "inner_factory", staticmethod(lambda: backend))
    return backend


class TestPinnedConnection:
    async def test_connects_to_the_vetted_address(self, monkeypatch, fake_socket_layer):
        dns = _SequencedDNS({"example.org": ["93.184.216.34"]})
        monkeypatch.setattr(url_guard, "_getaddrinfo", dns)

        await proxy_mod._PinnedBackend().connect_tcp("example.org", 443)
        assert fake_socket_layer.connected == [("93.184.216.34", 443)]

    async def test_rebinding_name_is_resolved_once(self, monkeypatch, fake_socket_layer):
        """Public first, loopback second: the second answer is never asked for."""
        dns = _SequencedDNS({"rebind.example.org": ["93.184.216.34", "127.0.0.1"]})
        monkeypatch.setattr(url_guard, "_getaddrinfo", dns)

        await proxy_mod._PinnedBackend().connect_tcp("rebind.example.org", 80)
        assert dns.calls == ["rebind.example.org"]
        assert fake_socket_layer.connected == [("93.184.216.34", 80)]

    async def test_private_answer_is_refused_before_connecting(self, monkeypatch, fake_socket_layer):
        monkeypatch.setattr(url_guard, "_getaddrinfo", _SequencedDNS({"evil.example.org": ["10.1.2.3"]}))
        with pytest.raises(ValueError):
            await proxy_mod._PinnedBackend().connect_tcp("evil.example.org", 80)
        assert fake_socket_layer.connected == []

    async def test_unresolvable_host_is_refused(self, monkeypatch, fake_socket_layer):
        monkeypatch.setattr(url_guard, "_getaddrinfo", _SequencedDNS({}))
        with pytest.raises(ValueError):
            await proxy_mod._PinnedBackend().connect_tcp("gone.example.org", 80)
        assert fake_socket_layer.connected == []

    async def test_direct_client_is_built_on_the_pinned_transport(self, monkeypatch):
        _CapturingClient.captured = {}
        monkeypatch.setattr(proxy_mod.httpx, "AsyncClient", _CapturingClient)
        await proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="direct")).get("http://x.example.org")

        transport = _CapturingClient.captured["init"].get("transport")
        assert transport is not None, "direct mode must not fall back to httpx's own resolver"
        assert isinstance(transport._pool._network_backend, proxy_mod._PinnedBackend)

    async def test_proxied_client_has_no_local_resolution(self, monkeypatch):
        _CapturingClient.captured = {}
        monkeypatch.setattr(proxy_mod.httpx, "AsyncClient", _CapturingClient)
        await proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="vpn")).get("http://x.example.org")
        assert "transport" not in _CapturingClient.captured["init"]


class TestThroughHttpx:
    """The same guarantees, end to end through a real httpx client."""

    async def test_fetch_goes_to_the_vetted_address(self, monkeypatch, fake_socket_layer):
        monkeypatch.setattr(url_guard, "_getaddrinfo", _SequencedDNS({"example.org": ["93.184.216.34", "127.0.0.1"]}))
        fake_socket_layer.responses["93.184.216.34"] = _http(b"hello")

        resp = await proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="direct")).get("http://example.org/a")
        assert resp.text == "hello"
        assert fake_socket_layer.connected == [("93.184.216.34", 80)]

    async def test_redirect_to_a_rebinding_host_is_refused(self, monkeypatch, fake_socket_layer):
        monkeypatch.setattr(url_guard, "_getaddrinfo", _SequencedDNS({
            "example.org": ["93.184.216.34"],
            "inside.example.org": ["172.17.0.2"],
        }))
        fake_socket_layer.responses["93.184.216.34"] = _http(
            b"", "302 Found", "Location: http://inside.example.org/admin\r\n",
        )

        with pytest.raises(ValueError):
            await proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="direct")).get("http://example.org/a")
        assert [ip for ip, _ in fake_socket_layer.connected] == ["93.184.216.34"]

    async def test_redirect_to_an_ip_literal_is_refused(self, monkeypatch, fake_socket_layer):
        monkeypatch.setattr(url_guard, "_getaddrinfo", _SequencedDNS({"example.org": ["93.184.216.34"]}))
        fake_socket_layer.responses["93.184.216.34"] = _http(
            b"", "302 Found", "Location: http://169.254.169.254/latest/meta-data/\r\n",
        )
        with pytest.raises(ValueError):
            await proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="direct")).get("http://example.org/a")
        assert [ip for ip, _ in fake_socket_layer.connected] == ["93.184.216.34"]


# ---------------------------------------------------------------------------
# Response bodies are capped while they stream (C-6)
# ---------------------------------------------------------------------------
#
# ProxiedClient read every body whole before returning it. Feeds, api_feed and
# every enrichment provider go through it, so one hostile or broken endpoint
# could hand the API process an unbounded body to hold in memory.


@pytest.fixture
def example_org(monkeypatch, fake_socket_layer):
    monkeypatch.setattr(url_guard, "_getaddrinfo", _SequencedDNS({"example.org": ["93.184.216.34"]}))
    return fake_socket_layer


def _direct_client(**kwargs):
    return proxy_mod.ProxiedClient(proxy_mod.ProxyConfig(mode="direct"), **kwargs)


class TestBodyCap:
    async def test_declared_oversized_body_is_refused(self, example_org):
        example_org.responses["93.184.216.34"] = _http(b"x" * 2000)
        with pytest.raises(proxy_mod.ResponseTooLarge):
            await _direct_client().get("http://example.org/big", max_bytes=1000)

    async def test_undeclared_oversized_body_is_refused_while_streaming(self, example_org):
        """No Content-Length to check up front: the cap is enforced on the bytes."""
        chunk = b"y" * 600
        example_org.responses["93.184.216.34"] = [
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n",
            b"258\r\n" + chunk + b"\r\n",
            b"258\r\n" + chunk + b"\r\n",
            b"0\r\n\r\n",
        ]
        with pytest.raises(proxy_mod.ResponseTooLarge):
            await _direct_client(max_bytes=1000).get("http://example.org/stream")

    async def test_too_large_is_an_httpx_error(self):
        """Enrichment providers already treat httpx.HTTPError as a transport
        failure, so the new refusal needs no new handling there."""
        assert issubclass(proxy_mod.ResponseTooLarge, proxy_mod.httpx.HTTPError)

    async def test_body_under_the_cap_reads_normally(self, example_org):
        example_org.responses["93.184.216.34"] = _http(
            b'{"ok": true}', extra="Content-Type: application/json\r\n",
        )
        resp = await _direct_client().get("http://example.org/api", max_bytes=1000)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        resp.raise_for_status()

    async def test_compressed_body_is_decoded_exactly_once(self, example_org):
        import gzip

        body = gzip.compress(b"plain text body")
        example_org.responses["93.184.216.34"] = _http(body, extra="Content-Encoding: gzip\r\n")
        resp = await _direct_client().get("http://example.org/gz")
        assert resp.text == "plain text body"

    async def test_decompressed_size_is_what_counts(self, example_org):
        """A small gzip that inflates past the cap is still too large."""
        import gzip

        bomb = gzip.compress(b"z" * 50_000)
        assert len(bomb) < 1000
        example_org.responses["93.184.216.34"] = _http(bomb, extra="Content-Encoding: gzip\r\n")
        with pytest.raises(proxy_mod.ResponseTooLarge):
            await _direct_client().get("http://example.org/bomb", max_bytes=10_000)

    async def test_fetch_text_honours_the_cap(self, example_org):
        example_org.responses["93.184.216.34"] = _http(b"x" * 2000)
        with pytest.raises(proxy_mod.ResponseTooLarge):
            await _direct_client(max_bytes=1000).fetch_text("http://example.org/feed")

    def test_default_cap_is_ten_megabytes(self):
        assert proxy_mod._fetch_cap(None) == 10_000_000
