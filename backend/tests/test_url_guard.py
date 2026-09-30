"""SSRF guard used by every collection fetch path (crawl_urls, scraper, agentic, ProxiedClient).

No test here performs a real DNS lookup: IP-literal hosts resolve to themselves,
and anything else goes through the ``dns`` fixture's table.
"""
import socket
from types import SimpleNamespace

import pytest

from intel_platform.collection import url_guard
from intel_platform.collection.url_guard import (
    is_safe_url,
    is_safe_url_async,
    validate_url,
    validate_url_async,
)


@pytest.fixture
def dns(monkeypatch):
    """A resolver backed by a table; unknown names fail like a real NXDOMAIN."""
    state = SimpleNamespace(table={}, calls=[])

    def fake_getaddrinfo(host):
        state.calls.append(host)
        if host not in state.table:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
            for ip in state.table[host]
        ]

    monkeypatch.setattr(url_guard, "_getaddrinfo", fake_getaddrinfo)
    return state


def test_blocks_internal_service_hostnames():
    assert not is_safe_url("http://localhost/")
    assert not is_safe_url("http://neo4j:7687/")
    assert not is_safe_url("http://postgres/")
    assert not is_safe_url("http://metadata.google.internal/latest/meta-data/")


def test_blocks_non_http_schemes():
    assert not is_safe_url("ftp://example.com/resource")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("gopher://example.com/")


def test_blocks_urls_without_hostname():
    assert not is_safe_url("http:///no-host")


def test_allows_ordinary_public_https_url():
    # IP-literal host resolves to itself; a global address must pass the guard.
    assert is_safe_url("https://8.8.8.8/")


class TestResolution:
    def test_unresolvable_host_is_unsafe(self, dns):
        """A lookup failure used to be swallowed and the URL passed. The fetcher
        then resolved it itself — possibly differently — so the guard vetted
        nothing. Fail closed."""
        assert not is_safe_url("https://no-such-host.example.org/")

    def test_host_resolving_to_private_address_is_unsafe(self, dns):
        dns.table["rebind.example.org"] = ["10.0.0.5"]
        assert not is_safe_url("https://rebind.example.org/")

    def test_one_private_address_among_several_is_unsafe(self, dns):
        dns.table["mixed.example.org"] = ["93.184.216.34", "127.0.0.1"]
        assert not is_safe_url("https://mixed.example.org/")

    def test_public_host_returns_the_vetted_addresses(self, dns):
        dns.table["example.org"] = ["93.184.216.34"]
        assert validate_url("https://example.org/page") == ["93.184.216.34"]

    async def test_async_form_resolves_off_the_loop_and_agrees(self, dns):
        dns.table["example.org"] = ["93.184.216.34"]
        dns.table["rebind.example.org"] = ["169.254.169.254"]
        assert await validate_url_async("https://example.org/") == ["93.184.216.34"]
        assert not await is_safe_url_async("https://rebind.example.org/")
        assert not await is_safe_url_async("https://no-such-host.example.org/")


class TestProxyModeSkipsLocalResolution:
    """Behind Tor or a VPN the target is resolved at the far end. Resolving it
    locally leaks every hostname to the local resolver, and its answer is not
    the one the proxy will use anyway."""

    def test_no_lookup_is_made(self, dns):
        assert validate_url("https://example.org/", resolve=False) == []
        assert dns.calls == []

    async def test_no_lookup_is_made_async(self, dns):
        assert await is_safe_url_async("https://example.org/", resolve=False)
        assert dns.calls == []

    @pytest.mark.parametrize("url", [
        "http://10.0.0.1/",
        "http://127.0.0.1:8000/api/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://neo4j:7474/",
        "http://gluetun:8000/",
        "http://host.docker.internal/",
        "http://api.localhost/",
        "http://localhost./",
        # Legacy IPv4 spellings a browser parses as 127.0.0.1. With no local
        # lookup to expand them, the guard must read them the way Chromium does.
        "http://2130706433/",
        "http://0x7f.1/",
        "http://127.1/",
        "http://0177.0.0.1/",
        # Parsers disagree on a backslash: urllib reads the host as example.org,
        # a browser as 127.0.0.1.
        "http://127.0.0.1\\@example.org/",
    ])
    def test_literal_and_name_checks_still_apply(self, dns, url):
        with pytest.raises(ValueError):
            validate_url(url, resolve=False)
        assert dns.calls == []
