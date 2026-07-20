"""SSRF guard used by every collection fetch path (crawl_urls, scraper, agentic).

These assertions are scheme/blocklist-based, so they need no DNS.
"""
from intel_platform.collection.url_guard import is_safe_url


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
