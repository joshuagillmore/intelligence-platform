# Backend — `intel_platform`

FastAPI service: the collection → extraction → graph → analysis engine. Python
**3.11**, managed entirely with **`uv`**. See the root `CLAUDE.md` for
architecture, branching, and the deploy story.

## Commands (uv only — never bare `python`/`pip`)

```bash
uv sync                                              # install/lock deps
uv run uvicorn intel_platform.api.app:app --reload   # run API on :8000
uv run pytest                                         # tests (asyncio auto-mode)
uv run pytest tests/test_x.py::test_y -v              # one test
uv run ruff check .                                   # lint (line-length 120, py311)
uv run ruff format .                                  # format
```

Tests live in `backend/tests/` (`testpaths=["tests"]`, `asyncio_mode = "auto"` —
just write `async def test_...`, no decorator needed).

## Package map (`src/intel_platform/`)

| Package | Responsibility |
|---------|----------------|
| `api/` | FastAPI app + `routes/` (24 routers: auth, documents, entities, graph, collections, collection_plans, query, assess, topics, reports, geo, timeline, search, watchlist, personas, snapshots, admin_config, llm, ingest, export, notebook, projects, health). App = `api.app:app`; middleware = rate-limit / request-logging / security-headers. |
| `services/` | Business logic (18): extraction, enrichment, ingestion, graph_builder, graph_rag, hybrid_retrieval, vector_search, document_clustering, topics, assessment, summarization, geocoding, collection_planner, plan_executor, reports, mindmap_export, graph_cache, text_utils. |
| `collection/` | Agentic web collection: `search` (ddgs) → `crawler`/`scraper` (crawl4ai) → `runner`/`executor` (CollectionRunner) → ingest. `tasks.py` = Celery. `agentic.py` = LLM-driven planning. |
| `llm/` | Multi-provider layer: `anthropic`, `openai_provider`, `cohere_provider`, `ollama`, plus `embeddings`, `skills`, and the **`orchestrator`** (provider selection — the single source of truth). |
| `graph/` | Neo4j: `schema.py` (`initialize_schema`), `store.py`. |
| `db/` | Postgres (SQLAlchemy async): `engine.py` (`init_db`), `models.py`. |
| `models/` | Pydantic v2 domain: `entities`, `relationships`, `type_hierarchy`, `requests`, `responses`. |
| `connectors/`, `data/`, `mcp/` | External connectors, seed/data, and an MCP server surface. |

## Data stores

- **Neo4j** — the knowledge graph (entities + relationships). Schema is created
  at app startup (`graph.schema.initialize_schema`). Local: `bolt://localhost:7687`
  (`neo4j` / `changeme`). Access via `api.deps.get_neo4j_driver`.
- **Postgres + pgvector** — documents, embeddings, and collection-plan state.
  Async SQLAlchemy; tables initialized at startup via `db.engine.init_db()`
  (no Alembic migration flow yet — schema is created on boot).

## LLM providers

Provider-agnostic. Pick via config (`default_llm_provider`, `default_llm_model`;
`.env.example` ships Ollama + `qwen2.5:14b` for local, code default is
`anthropic`). **Always go through `llm/orchestrator.py`** — do not re-add
per-module provider selection. Embeddings default to OpenAI (1536-dim), also
Cohere/Ollama.

## Conventions

- **Async everywhere** (FastAPI + async SQLAlchemy + async Neo4j/httpx).
- **Pydantic v2** models for all request/response shapes (`models/`).
- Config only via `intel_platform.config.Settings` (pydantic-settings) — never
  read `os.environ` ad hoc in business logic.
- Don't leak internal error detail to API clients (past review finding);
  log server-side, return clean errors.
- Watch the collection scraper's SSRF guard — keep URL scheme/host validation
  when editing `collection/scraper.py`.

## Definition of done

`uv run pytest` green **and** `uv run ruff check .` clean. No exceptions.
