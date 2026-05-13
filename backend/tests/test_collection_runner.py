import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from intel_platform.collection.runner import CollectionRunner


@pytest.fixture
def mock_store():
    store = MagicMock()
    store._driver = MagicMock()
    session_mock = MagicMock()
    store._driver.session.return_value.__enter__ = MagicMock(return_value=session_mock)
    store._driver.session.return_value.__exit__ = MagicMock(return_value=False)
    session_mock.run = MagicMock()
    store.create_entity = MagicMock()
    store.create_relationship = MagicMock()
    store.search_entity_by_name = MagicMock(return_value=[])
    return store


@pytest.mark.asyncio
async def test_runner_executes_web_search_plan(mock_store):
    plan = [
        {"id": 1, "description": "Search for Iran sanctions news", "source_type": "web_search", "approved": True},
    ]

    with patch("intel_platform.collection.runner.web_search") as mock_search, \
         patch("intel_platform.collection.runner.crawl_urls", new_callable=AsyncMock) as mock_crawl, \
         patch("intel_platform.collection.runner.extract_entities_nlp") as mock_extract:

        mock_search.return_value = [
            {"url": "https://example.com/article", "title": "Iran Sanctions", "snippet": "..."},
        ]
        mock_crawl.return_value = [
            {"url": "https://example.com/article", "title": "Iran Sanctions", "content": "Iran faces new sanctions from the EU.", "raw_markdown": "...", "word_count": 7, "links_internal": 0, "links_external": 0},
        ]
        mock_extract.return_value = (
            [{"name": "Iran", "entity_type": "Location"}],
            [{"source_name": "Iran", "target_name": "EU", "rel_type": "ASSOCIATED_WITH", "confidence": 0.7}],
        )

        runner = CollectionRunner(mock_store)
        result = await runner.execute(
            collection_id="coll-1",
            project_id="proj-1",
            plan=plan,
        )

    assert result["documents_crawled"] >= 1
    mock_search.assert_called_once()
    mock_crawl.assert_called_once()


@pytest.mark.asyncio
async def test_runner_skips_unapproved_items(mock_store):
    plan = [
        {"id": 1, "description": "Approved item", "source_type": "web_search", "approved": True},
        {"id": 2, "description": "Not approved", "source_type": "web_search", "approved": False},
    ]

    with patch("intel_platform.collection.runner.web_search") as mock_search, \
         patch("intel_platform.collection.runner.crawl_urls", new_callable=AsyncMock) as mock_crawl, \
         patch("intel_platform.collection.runner.extract_entities_nlp") as mock_extract:

        mock_search.return_value = []
        mock_crawl.return_value = []
        mock_extract.return_value = ([], [])

        runner = CollectionRunner(mock_store)
        await runner.execute(collection_id="coll-1", project_id="proj-1", plan=plan)

    assert mock_search.call_count == 1


@pytest.mark.asyncio
async def test_runner_handles_crawl_failure(mock_store):
    plan = [
        {"id": 1, "description": "Search test", "source_type": "web_search", "approved": True},
    ]

    with patch("intel_platform.collection.runner.web_search") as mock_search, \
         patch("intel_platform.collection.runner.crawl_urls", new_callable=AsyncMock) as mock_crawl, \
         patch("intel_platform.collection.runner.extract_entities_nlp"):

        mock_search.return_value = [{"url": "https://example.com", "title": "Test", "snippet": "..."}]
        mock_crawl.return_value = []  # All crawls failed

        runner = CollectionRunner(mock_store)
        result = await runner.execute(collection_id="coll-1", project_id="proj-1", plan=plan)

    assert result["documents_crawled"] == 0
    assert result["status"] == "SUCCESS"
