import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from intel_platform.collection.proxy import ProxyConfig

# IP-literal hosts: they resolve to themselves, so the SSRF pre-filter vets them
# without a DNS query and these tests make no network request.
GOOD = "https://93.184.216.34/good"
BAD = "https://93.184.216.35/bad"


@pytest.fixture(autouse=True)
def direct_mode(monkeypatch):
    """Pin the proxy mode so crawl_urls does not wait on Postgres to read it."""
    async def _direct():
        return ProxyConfig(mode="direct")

    monkeypatch.setattr("intel_platform.collection.crawler.get_active_proxy_config", _direct)


@pytest.mark.asyncio
async def test_crawl_urls_returns_documents():
    from intel_platform.collection.crawler import crawl_urls

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.url = GOOD
    mock_result.redirected_url = GOOD
    mock_result.markdown = MagicMock()
    mock_result.markdown.raw_markdown = "# Hello World\nSome content here."
    mock_result.markdown.fit_markdown = "Some content here."
    mock_result.metadata = {"title": "Example Page"}
    mock_result.links = {"internal": ["/about"], "external": ["https://other.com"]}
    mock_result.error_message = None

    with patch("intel_platform.collection.crawler.AsyncWebCrawler") as MockCrawler:
        instance = MockCrawler.return_value
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.arun_many = AsyncMock(return_value=[mock_result])

        docs = await crawl_urls([GOOD])

    assert len(docs) == 1
    assert docs[0]["url"] == GOOD
    assert docs[0]["title"] == "Example Page"
    assert "content" in docs[0]
    assert docs[0]["word_count"] > 0


@pytest.mark.asyncio
async def test_crawl_urls_skips_failures():
    from intel_platform.collection.crawler import crawl_urls

    success = MagicMock()
    success.success = True
    success.url = GOOD
    success.redirected_url = GOOD
    success.markdown = MagicMock()
    success.markdown.raw_markdown = "Good content"
    success.markdown.fit_markdown = "Good content"
    success.metadata = {"title": "Good"}
    success.links = {"internal": [], "external": []}
    success.error_message = None

    failure = MagicMock()
    failure.success = False
    failure.url = BAD
    failure.error_message = "Timeout"

    with patch("intel_platform.collection.crawler.AsyncWebCrawler") as MockCrawler:
        instance = MockCrawler.return_value
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.arun_many = AsyncMock(return_value=[success, failure])

        docs = await crawl_urls([GOOD, BAD])

    assert len(docs) == 1
    assert docs[0]["url"] == GOOD


@pytest.mark.asyncio
async def test_crawl_urls_empty_list():
    from intel_platform.collection.crawler import crawl_urls

    docs = await crawl_urls([])
    assert docs == []
