from intel_platform.collection.proxy import ProxyConfig, ProxiedClient


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
