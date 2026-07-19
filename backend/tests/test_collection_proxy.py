from unittest.mock import patch

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

    MockDDGS.assert_called_once()
    _, kwargs = MockDDGS.call_args
    assert kwargs.get("proxy") == "socks5h://tor:9050"


def test_web_search_defaults_to_no_proxy():
    from intel_platform.collection.search import web_search

    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = []
        web_search("q", max_results=5)

    _, kwargs = MockDDGS.call_args
    assert kwargs.get("proxy") is None
