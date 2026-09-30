import uuid

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from intel_platform.collection.proxy import ProxyConfig
from intel_platform.collection.runner import CollectionRunner
from intel_platform.config import settings


@pytest.fixture(autouse=True)
def direct_mode(monkeypatch):
    """Pin the proxy mode: reading it from an absent Postgres cost 60 s a test."""
    async def _direct():
        return ProxyConfig(mode="direct")

    monkeypatch.setattr("intel_platform.collection.runner.get_active_proxy_config", _direct)


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
    # Every approved item found pages and none could be crawled: that is a
    # failed collection, not a successful one with nothing in it (C-14).
    assert result["status"] == "FAILURE"


# ---------------------------------------------------------------------------
# C-14: status reflects what happened, cancel works — against real Neo4j
# ---------------------------------------------------------------------------

PAGE ={"url": "https://news.example.org/a", "title": "A", "content": "Iran faces new sanctions from the EU.",
        "raw_markdown": "", "word_count": 7, "links_internal": 0, "links_external": 0}


def _collection(graph_store, status="PENDING"):
    cid = f"coll-{uuid.uuid4()}"
    with graph_store._driver.session() as s:
        s.run("CREATE (c:Collection {id: $id, project_id: 'test-legacy-runner', status: $status})",
              id=cid, status=status)
    return cid


def _status(graph_store, cid):
    with graph_store._driver.session() as s:
        return s.run("MATCH (c:Collection {id: $id}) RETURN c.status AS s", id=cid).single()["s"]


def _items(n):
    return [{"id": i, "description": f"item {i}", "source_type": "web_search", "approved": True} for i in range(n)]


class TestLegacyRunnerStatus:
    async def test_every_item_failing_is_a_failure(self, graph_store):
        cid = _collection(graph_store)
        with patch("intel_platform.collection.runner.web_search", return_value=[{"url": PAGE["url"]}]), \
             patch("intel_platform.collection.runner.crawl_urls", new=AsyncMock(side_effect=RuntimeError("no chromium"))):
            result = await CollectionRunner(graph_store).execute(cid, "test-legacy-runner", _items(2))

        assert result["status"] == "FAILURE"
        assert _status(graph_store, cid) == "FAILURE"

    async def test_some_items_failing_is_partial(self, graph_store):
        cid = _collection(graph_store)
        crawl = AsyncMock(side_effect=[[PAGE], RuntimeError("timeout")])
        with patch("intel_platform.collection.runner.web_search", return_value=[{"url": PAGE["url"]}]), \
             patch("intel_platform.collection.runner.crawl_urls", new=crawl), \
             patch("intel_platform.collection.runner.extract_entities_nlp", return_value=([], [])):
            result = await CollectionRunner(graph_store).execute(cid, "test-legacy-runner", _items(2))

        assert result["status"] == "PARTIAL"
        assert _status(graph_store, cid) == "PARTIAL"

    async def test_all_items_succeeding_is_success(self, graph_store):
        cid = _collection(graph_store)
        with patch("intel_platform.collection.runner.web_search", return_value=[{"url": PAGE["url"]}]), \
             patch("intel_platform.collection.runner.crawl_urls", new=AsyncMock(return_value=[PAGE])), \
             patch("intel_platform.collection.runner.extract_entities_nlp", return_value=([], [])):
            result = await CollectionRunner(graph_store).execute(cid, "test-legacy-runner", _items(1))

        assert result["status"] == "SUCCESS"
        assert _status(graph_store, cid) == "SUCCESS"

    async def test_cancel_between_items_stops_the_run(self, graph_store):
        """Cancel set REVOKED and the runner never looked: it ran every item and
        wrote SUCCESS over the cancellation."""
        cid = _collection(graph_store)
        searched = []

        def search(description, max_results=10, proxy=None):
            searched.append(description)
            return [{"url": PAGE["url"]}]

        async def crawl_then_cancel(urls, timeout_ms=30000):
            with graph_store._driver.session() as s:  # the analyst presses Cancel
                s.run("MATCH (c:Collection {id: $id}) SET c.status = 'REVOKED'", id=cid)
            return [PAGE]

        with patch("intel_platform.collection.runner.web_search", side_effect=search), \
             patch("intel_platform.collection.runner.crawl_urls", new=crawl_then_cancel), \
             patch("intel_platform.collection.runner.extract_entities_nlp", return_value=([], [])):
            result = await CollectionRunner(graph_store).execute(cid, "test-legacy-runner", _items(3))

        assert searched == ["item 0"], "items after the cancel still ran"
        assert result["status"] == "REVOKED"
        assert _status(graph_store, cid) == "REVOKED"

    async def test_a_cancelled_collection_can_be_run_again(self, graph_store):
        cid = _collection(graph_store, status="REVOKED")
        with patch("intel_platform.collection.runner.web_search", return_value=[{"url": PAGE["url"]}]), \
             patch("intel_platform.collection.runner.crawl_urls", new=AsyncMock(return_value=[PAGE])), \
             patch("intel_platform.collection.runner.extract_entities_nlp", return_value=([], [])):
            result = await CollectionRunner(graph_store).execute(cid, "test-legacy-runner", _items(1))

        assert result["status"] == "SUCCESS"
        assert _status(graph_store, cid) == "SUCCESS"

    async def test_content_is_bounded_by_max_document_chars(self, graph_store, monkeypatch):
        monkeypatch.setattr(settings, "max_document_chars", 100)
        cid = _collection(graph_store)
        long_page = {**PAGE, "content": "Sanctions on shipping. " * 50}
        stored = []
        original = graph_store.create_entity

        def capture(entity):
            stored.append(entity)
            return original(entity)

        monkeypatch.setattr(graph_store, "create_entity", capture)
        with patch("intel_platform.collection.runner.web_search", return_value=[{"url": PAGE["url"]}]), \
             patch("intel_platform.collection.runner.crawl_urls", new=AsyncMock(return_value=[long_page])), \
             patch("intel_platform.collection.runner.extract_entities_nlp", return_value=([], [])):
            await CollectionRunner(graph_store).execute(cid, "test-legacy-runner", _items(1))

        assert len(stored[0].content) <= 100
