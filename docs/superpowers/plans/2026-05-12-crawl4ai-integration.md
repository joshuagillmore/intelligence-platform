# Crawl4ai Agentic Collections Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the crawl4ai library into Sentinel's collection pipeline so that approved collection plans automatically search the web, crawl results with a headless browser, and feed extracted content into the existing entity extraction + graph building pipeline.

**Architecture:** Replace the static BeautifulSoup scraper with crawl4ai's `AsyncWebCrawler` (headless Chromium). Add a DuckDuckGo search module via `ddgs`. Create a `CollectionRunner` that executes collection plans as background async tasks with per-item progress updates persisted to Neo4j. Bridge crawled documents into the existing `ingest_text` → `extract_entities` → `build_graph_from_extractions` pipeline.

**Tech Stack:** crawl4ai (AsyncWebCrawler, BrowserConfig, CrawlerRunConfig), ddgs (DuckDuckGo search), asyncio, FastAPI BackgroundTasks, Neo4j

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/pyproject.toml` | Modify | Add `crawl4ai` and `ddgs` dependencies |
| `backend/Dockerfile` | Modify | Add `crawl4ai-setup` for Chromium install |
| `backend/src/intel_platform/collection/search.py` | Create | DuckDuckGo web search wrapper |
| `backend/src/intel_platform/collection/crawler.py` | Create | AsyncWebCrawler wrapper with progress callbacks |
| `backend/src/intel_platform/collection/runner.py` | Create | Plan execution orchestrator (search → crawl → ingest) |
| `backend/src/intel_platform/collection/scraper.py` | Modify | Rewrite to delegate to crawl4ai |
| `backend/src/intel_platform/api/routes/collections.py` | Modify | Add `/execute` and `/progress` endpoints |
| `backend/tests/test_collection_search.py` | Create | Tests for DuckDuckGo search wrapper |
| `backend/tests/test_collection_crawler.py` | Create | Tests for crawl4ai crawler wrapper |
| `backend/tests/test_collection_runner.py` | Create | Tests for plan execution orchestrator |
| `backend/tests/test_collection_execute_route.py` | Create | Tests for the execute API endpoint |

---

### Task 1: Add Dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Add crawl4ai and ddgs to pyproject.toml**

```toml
# In the dependencies list, add these two lines:
    "crawl4ai~=0.8.6",
    "ddgs~=9.0",
```

Add after the existing `"bcrypt~=4.0",` line in `pyproject.toml`.

- [ ] **Step 2: Update Dockerfile to install Chromium for crawl4ai**

Replace the current Dockerfile with:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY src/ src/

RUN uv sync --no-dev
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Install Chromium for crawl4ai headless browser
RUN uv run crawl4ai-setup

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "intel_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Verify dependency resolution locally**

Run: `cd backend && uv sync`
Expected: completes without errors, `crawl4ai` and `ddgs` installed.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/Dockerfile
git commit -m "deps: add crawl4ai and ddgs for agentic collection"
```

---

### Task 2: DuckDuckGo Search Wrapper

**Files:**
- Create: `backend/src/intel_platform/collection/search.py`
- Create: `backend/tests/test_collection_search.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_collection_search.py`:

```python
from unittest.mock import patch, MagicMock
from intel_platform.collection.search import web_search


def test_web_search_returns_results():
    mock_results = [
        {"href": "https://example.com/1", "title": "Result 1", "body": "Snippet 1"},
        {"href": "https://example.com/2", "title": "Result 2", "body": "Snippet 2"},
    ]
    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = mock_results
        results = web_search("test query", max_results=5)

    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["title"] == "Result 1"
    assert results[0]["snippet"] == "Snippet 1"


def test_web_search_max_results_clamped():
    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = []
        web_search("test", max_results=50)
        instance.text.assert_called_once()
        call_kwargs = instance.text.call_args
        assert call_kwargs[1].get("max_results", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else 20) <= 20


def test_web_search_handles_exception():
    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.side_effect = Exception("Network error")
        results = web_search("test query")

    assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_collection_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'intel_platform.collection.search'`

- [ ] **Step 3: Write the implementation**

Create `backend/src/intel_platform/collection/search.py`:

```python
from __future__ import annotations

import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 10) -> list[dict]:
    """Search the web via DuckDuckGo and return structured results."""
    max_results = min(max(1, max_results), 20)
    try:
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results)
            return [
                {
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
                if r.get("href")
            ]
    except Exception:
        logger.exception("DuckDuckGo search failed for query: %s", query)
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_collection_search.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/intel_platform/collection/search.py backend/tests/test_collection_search.py
git commit -m "feat: add DuckDuckGo web search wrapper for collections"
```

---

### Task 3: Crawl4ai Crawler Wrapper

**Files:**
- Create: `backend/src/intel_platform/collection/crawler.py`
- Create: `backend/tests/test_collection_crawler.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_collection_crawler.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_collection_crawler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `backend/src/intel_platform/collection/crawler.py`:

```python
from __future__ import annotations

import logging
from typing import Callable

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

logger = logging.getLogger(__name__)

_browser_cfg = BrowserConfig(headless=True, browser_type="chromium")


def _make_run_cfg(timeout_ms: int = 30000) -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=50,
        page_timeout=timeout_ms,
    )


async def crawl_urls(
    urls: list[str],
    timeout_ms: int = 30000,
    on_progress: Callable[[str, str], None] | None = None,
) -> list[dict]:
    """Crawl a list of URLs with headless Chromium and return structured documents.

    Args:
        urls: URLs to crawl.
        timeout_ms: Per-page timeout in milliseconds.
        on_progress: Optional callback(url, status) for progress tracking.

    Returns:
        List of document dicts with url, title, content, markdown, word_count, links.
    """
    if not urls:
        return []

    run_cfg = _make_run_cfg(timeout_ms)
    documents = []

    async with AsyncWebCrawler(config=_browser_cfg) as crawler:
        results = await crawler.arun_many(urls=urls, config=run_cfg)

        for result in results:
            if not result.success:
                logger.warning("Crawl failed for %s: %s", result.url, result.error_message)
                if on_progress:
                    on_progress(result.url, "error")
                continue

            raw_md = result.markdown.raw_markdown if result.markdown else ""
            fit_md = result.markdown.fit_markdown if result.markdown else ""
            content = fit_md or raw_md
            meta = result.metadata or {}
            links = result.links or {}

            documents.append({
                "url": result.url,
                "title": meta.get("title", ""),
                "content": content,
                "raw_markdown": raw_md,
                "word_count": len(content.split()) if content else 0,
                "links_internal": len(links.get("internal", [])),
                "links_external": len(links.get("external", [])),
            })

            if on_progress:
                on_progress(result.url, "done")

    return documents
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_collection_crawler.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/intel_platform/collection/crawler.py backend/tests/test_collection_crawler.py
git commit -m "feat: add crawl4ai browser-based crawler wrapper"
```

---

### Task 4: Rewrite WebScraper to Use Crawl4ai

**Files:**
- Modify: `backend/src/intel_platform/collection/scraper.py`

- [ ] **Step 1: Rewrite scraper.py to delegate to crawl4ai**

Replace `backend/src/intel_platform/collection/scraper.py` with:

```python
from __future__ import annotations

from urllib.parse import urlparse

from intel_platform.collection.crawler import crawl_urls


def _validate_url(url: str) -> None:
    """SSRF protection: reject non-HTTP schemes and private network URLs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or \
       hostname.startswith("169.254.") or hostname.startswith("10.") or \
       hostname.startswith("192.168."):
        raise ValueError("URLs pointing to internal/private networks are not allowed")


class WebScraper:
    """Scrape a single URL using crawl4ai's headless browser."""

    async def scrape_url(self, url: str, timeout: float = 30) -> dict:
        _validate_url(url)
        docs = await crawl_urls([url], timeout_ms=int(timeout * 1000))
        if not docs:
            raise RuntimeError(f"Failed to crawl {url}")
        doc = docs[0]
        return {
            "url": doc["url"],
            "title": doc["title"],
            "content": doc["content"],
            "content_length": len(doc["content"]),
        }
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd backend && uv run pytest tests/ -q -k "scraper or crawl" --ignore=tests/test_collection_crawler.py`
Expected: Any existing scraper tests pass (if none exist, that's fine — the module compiles)

- [ ] **Step 3: Commit**

```bash
git add backend/src/intel_platform/collection/scraper.py
git commit -m "refactor: rewrite WebScraper to use crawl4ai headless browser"
```

---

### Task 5: Collection Plan Runner (Orchestrator)

**Files:**
- Create: `backend/src/intel_platform/collection/runner.py`
- Create: `backend/tests/test_collection_runner.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_collection_runner.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_collection_runner.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `backend/src/intel_platform/collection/runner.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

from intel_platform.collection.search import web_search
from intel_platform.collection.crawler import crawl_urls
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Document
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.ingestion import ingest_text

logger = logging.getLogger(__name__)


class CollectionRunner:
    """Executes a collection plan: search → crawl → ingest → extract → graph."""

    def __init__(self, store: GraphStore):
        self._store = store

    async def execute(
        self,
        collection_id: str,
        project_id: str,
        plan: list[dict],
        extraction_mode: str = "nlp",
        on_progress: callable = None,
    ) -> dict:
        self._update_status(collection_id, "STARTED")
        approved_items = [item for item in plan if item.get("approved", False)]
        total_items = len(approved_items)

        all_urls: list[str] = []
        total_docs_crawled = 0
        total_entities = 0
        total_relationships = 0
        errors: list[dict] = []

        for idx, item in enumerate(approved_items):
            item_desc = item.get("description", "")
            source_type = item.get("source_type", "web_search")

            try:
                # Stage 1: Search
                urls = self._search_for_item(item_desc, source_type)
                all_urls.extend(urls)

                # Stage 2: Crawl
                documents = await crawl_urls(urls, timeout_ms=30000)

                # Stage 3: Ingest each crawled doc into the graph
                for doc_data in documents:
                    result = await self._ingest_document(
                        doc_data, project_id, collection_id, extraction_mode,
                    )
                    total_docs_crawled += 1
                    total_entities += result.get("entities_created", 0)
                    total_relationships += result.get("relationships_created", 0)

            except Exception:
                logger.exception("Plan item %d failed: %s", item.get("id", idx), item_desc)
                errors.append({"item_id": item.get("id", idx), "description": item_desc})

            # Update progress
            progress = (idx + 1) / total_items if total_items > 0 else 1.0
            self._update_status(
                collection_id, "PROGRESS",
                progress=progress, documents_acquired=total_docs_crawled,
            )
            if on_progress:
                on_progress(collection_id, progress, total_docs_crawled)

        self._update_status(
            collection_id, "SUCCESS",
            progress=1.0, documents_acquired=total_docs_crawled,
        )

        return {
            "collection_id": collection_id,
            "status": "SUCCESS",
            "items_processed": len(approved_items),
            "urls_found": len(all_urls),
            "documents_crawled": total_docs_crawled,
            "entities_created": total_entities,
            "relationships_created": total_relationships,
            "errors": errors,
        }

    def _search_for_item(self, description: str, source_type: str) -> list[str]:
        """Run a web search for a plan item and return URLs."""
        results = web_search(description, max_results=10)
        return [r["url"] for r in results if r.get("url")]

    async def _ingest_document(
        self, doc_data: dict, project_id: str, collection_id: str, extraction_mode: str,
    ) -> dict:
        """Create a Document node and run entity extraction."""
        content = doc_data.get("content", "")
        if not content.strip():
            return {"entities_created": 0, "relationships_created": 0}

        doc = Document(
            name=doc_data.get("title", "") or doc_data.get("url", "untitled"),
            content=content,
            url=doc_data.get("url", ""),
            reliability_rating="C4",
            project_id=project_id,
            source_doc_id=collection_id,
        )
        self._store.create_entity(doc)

        chunks = ingest_text(content, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)

        all_entities: list[dict] = []
        all_relationships: list[dict] = []
        for chunk in chunks:
            if extraction_mode == "llm":
                from intel_platform.services.extraction import extract_entities_llm
                ents, rels = await extract_entities_llm(chunk["content"], doc.id)
            elif extraction_mode == "hybrid":
                from intel_platform.services.extraction import extract_entities_hybrid
                ents, rels = await extract_entities_hybrid(chunk["content"], doc.id)
            else:
                ents, rels = extract_entities_nlp(chunk["content"], doc.id)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        return build_graph_from_extractions(
            self._store, all_entities, all_relationships, project_id, source_doc_id=doc.id,
        )

    def _update_status(
        self, collection_id: str, status: str,
        progress: float = 0.0, documents_acquired: int = 0,
    ) -> None:
        """Persist collection status to Neo4j."""
        now = datetime.now(timezone.utc).isoformat()
        with self._store._driver.session() as session:
            session.run(
                """
                MATCH (c:Collection {id: $id})
                SET c.status = $status, c.progress = $progress,
                    c.documents_acquired = $docs, c.updated_at = $now
                """,
                id=collection_id, status=status,
                progress=progress, docs=documents_acquired, now=now,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_collection_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/intel_platform/collection/runner.py backend/tests/test_collection_runner.py
git commit -m "feat: add CollectionRunner orchestrator (search → crawl → ingest)"
```

---

### Task 6: Wire Execute Endpoint into Collections API

**Files:**
- Modify: `backend/src/intel_platform/api/routes/collections.py`
- Create: `backend/tests/test_collection_execute_route.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_collection_execute_route.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from intel_platform.api.app import app
    return TestClient(app)


@pytest.fixture
def auth_header():
    from intel_platform.api.auth import create_access_token
    token = create_access_token("admin", "admin")
    return {"Authorization": f"Bearer {token}"}


def test_execute_collection_returns_202(client, auth_header):
    """POST /api/collections/{id}/execute should return 202 Accepted."""
    # Create a mock collection in Neo4j
    with patch("intel_platform.api.routes.collections.get_collection") as mock_get:
        mock_get.return_value = {
            "id": "coll-test",
            "project_id": "proj-1",
            "plan": [{"id": 1, "description": "test", "source_type": "web_search", "approved": True}],
            "status": "PENDING",
        }

        with patch("intel_platform.api.routes.collections.CollectionRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.execute = AsyncMock(return_value={
                "collection_id": "coll-test",
                "status": "SUCCESS",
                "documents_crawled": 2,
                "entities_created": 5,
                "relationships_created": 3,
                "items_processed": 1,
                "urls_found": 3,
                "errors": [],
            })
            MockRunner.return_value = mock_runner_instance

            response = client.post("/api/collections/coll-test/execute", headers=auth_header)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "STARTED"
    assert "collection_id" in data


def test_execute_collection_rejects_already_running(client, auth_header):
    """Cannot execute a collection that is already running."""
    with patch("intel_platform.api.routes.collections.get_collection") as mock_get:
        mock_get.return_value = {
            "id": "coll-test",
            "project_id": "proj-1",
            "plan": [],
            "status": "PROGRESS",
        }

        response = client.post("/api/collections/coll-test/execute", headers=auth_header)

    assert response.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_collection_execute_route.py -v`
Expected: FAIL — no `/execute` endpoint exists

- [ ] **Step 3: Add the execute and progress endpoints to collections.py**

Add these imports to the top of `backend/src/intel_platform/api/routes/collections.py`:

```python
import asyncio
import logging
from fastapi import BackgroundTasks
from intel_platform.collection.runner import CollectionRunner
```

Add `logger` after the router definition:

```python
logger = logging.getLogger(__name__)
```

Add these two endpoints at the end of the file (before the `list_collections` and `get_collection_count_for_project` routes — the order doesn't matter for FastAPI, just add them before the catch-all routes):

```python
@router.post("/collections/{task_id}/execute", status_code=202)
async def execute_collection(
    task_id: str,
    background_tasks: BackgroundTasks,
    extraction_mode: str = "nlp",
    store: GraphStore = Depends(get_graph_store),
):
    """Execute an approved collection plan: search → crawl → ingest → extract."""
    coll = get_collection(task_id, store)
    if coll["status"] in ("STARTED", "PROGRESS"):
        raise HTTPException(status_code=409, detail="Collection is already running")

    plan = coll.get("plan", [])
    if not any(item.get("approved") for item in plan):
        raise HTTPException(status_code=400, detail="No approved plan items to execute")

    async def _run():
        try:
            runner = CollectionRunner(store)
            await runner.execute(
                collection_id=task_id,
                project_id=coll["project_id"],
                plan=plan,
                extraction_mode=extraction_mode,
            )
        except Exception:
            logger.exception("Collection execution failed: %s", task_id)
            now = datetime.now(timezone.utc).isoformat()
            with store._driver.session() as session:
                session.run(
                    "MATCH (c:Collection {id: $id}) SET c.status = 'FAILURE', c.updated_at = $now",
                    id=task_id, now=now,
                )

    background_tasks.add_task(asyncio.create_task, _run())

    return {"collection_id": task_id, "status": "STARTED"}


@router.get("/collections/{task_id}/progress")
def get_collection_progress(task_id: str, store: GraphStore = Depends(get_graph_store)):
    """Get detailed collection execution progress."""
    coll = get_collection(task_id, store)
    # Count documents linked to this collection
    with store._driver.session() as session:
        result = session.run(
            "MATCH (d:Document {source_doc_id: $cid, project_id: $pid}) RETURN count(d) as cnt",
            cid=task_id, pid=coll["project_id"],
        )
        record = result.single()
        doc_count = record["cnt"] if record else 0

    return {
        "collection_id": task_id,
        "status": coll.get("status", "PENDING"),
        "progress": coll.get("progress", 0),
        "documents_acquired": coll.get("documents_acquired", 0),
        "documents_in_graph": doc_count,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_collection_execute_route.py -v`
Expected: 2 passed

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd backend && SPACY_MODEL=en_core_web_sm uv run pytest tests/ -q -k "not test_refine_labels_no_provider and not test_extract_persons" --tb=short`
Expected: All previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/src/intel_platform/api/routes/collections.py backend/tests/test_collection_execute_route.py
git commit -m "feat: add /execute and /progress endpoints to collections API"
```

---

### Task 7: Clean Up Legacy Code

**Files:**
- Modify: `backend/src/intel_platform/collection/executor.py`
- Modify: `backend/src/intel_platform/collection/tasks.py`

- [ ] **Step 1: Remove legacy executor and in-memory task manager**

These are replaced by `CollectionRunner` (which uses Neo4j for state) and the new execute endpoint.

Replace `backend/src/intel_platform/collection/executor.py` with:

```python
# Legacy CollectionExecutor replaced by collection.runner.CollectionRunner
# Kept as empty module to avoid import errors in any external references.
```

Replace `backend/src/intel_platform/collection/tasks.py` with:

```python
# Legacy in-memory CollectionManager replaced by Neo4j-backed collections.
# TaskStatus enum preserved for backwards compatibility with collection status values.
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"
```

- [ ] **Step 2: Verify no imports break**

Run: `cd backend && uv run python -c "from intel_platform.collection.tasks import TaskStatus; print(TaskStatus.PENDING)"`
Expected: `PENDING`

- [ ] **Step 3: Run full test suite**

Run: `cd backend && SPACY_MODEL=en_core_web_sm uv run pytest tests/ -q -k "not test_refine_labels_no_provider and not test_extract_persons" --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/src/intel_platform/collection/executor.py backend/src/intel_platform/collection/tasks.py
git commit -m "cleanup: remove legacy in-memory executor, replaced by CollectionRunner"
```

---

### Task 8: Docker Build and Local Deploy Verification

**Files:** None new — validation only.

- [ ] **Step 1: Build Docker images**

Run: `docker compose up -d --build`
Expected: Both backend and frontend build successfully. The backend image now includes Chromium for crawl4ai.

- [ ] **Step 2: Verify health endpoint**

Run: `curl -s http://localhost:8000/health`
Expected: `{"status":"...","neo4j_connected":true,...}`

- [ ] **Step 3: Verify new endpoints exist in OpenAPI schema**

Run: `curl -s http://localhost:8000/openapi.json | python -m json.tool | grep -E "execute|progress"`
Expected: Both `/api/collections/{task_id}/execute` and `/api/collections/{task_id}/progress` appear.

- [ ] **Step 4: End-to-end smoke test (manual)**

1. Create a project via the frontend
2. Create a collection with a PIR like "Recent cyber attacks on financial institutions"
3. Approve at least one plan item
4. Execute the collection via: `curl -X POST http://localhost:8000/api/collections/{id}/execute -H "Authorization: Bearer {token}"`
5. Poll progress: `curl http://localhost:8000/api/collections/{id}/progress -H "Authorization: Bearer {token}"`
6. Verify documents and entities appear in the knowledge graph

- [ ] **Step 5: Push to GitHub (triggers Railway deploy)**

```bash
git push origin main
```

- [ ] **Step 6: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final adjustments from integration testing"
```
