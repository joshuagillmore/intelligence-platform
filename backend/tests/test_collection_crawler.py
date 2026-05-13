import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_crawl_urls_returns_documents():
    from intel_platform.collection.crawler import crawl_urls

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.url = "https://example.com"
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

        docs = await crawl_urls(["https://example.com"])

    assert len(docs) == 1
    assert docs[0]["url"] == "https://example.com"
    assert docs[0]["title"] == "Example Page"
    assert "content" in docs[0]
    assert docs[0]["word_count"] > 0


@pytest.mark.asyncio
async def test_crawl_urls_skips_failures():
    from intel_platform.collection.crawler import crawl_urls

    success = MagicMock()
    success.success = True
    success.url = "https://good.com"
    success.markdown = MagicMock()
    success.markdown.raw_markdown = "Good content"
    success.markdown.fit_markdown = "Good content"
    success.metadata = {"title": "Good"}
    success.links = {"internal": [], "external": []}
    success.error_message = None

    failure = MagicMock()
    failure.success = False
    failure.url = "https://bad.com"
    failure.error_message = "Timeout"

    with patch("intel_platform.collection.crawler.AsyncWebCrawler") as MockCrawler:
        instance = MockCrawler.return_value
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.arun_many = AsyncMock(return_value=[success, failure])

        docs = await crawl_urls(["https://good.com", "https://bad.com"])

    assert len(docs) == 1
    assert docs[0]["url"] == "https://good.com"


@pytest.mark.asyncio
async def test_crawl_urls_empty_list():
    from intel_platform.collection.crawler import crawl_urls

    docs = await crawl_urls([])
    assert docs == []
