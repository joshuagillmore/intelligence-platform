# Backend — `intel_platform`

FastAPI service: the collection → extraction → graph → analysis engine. Python
**3.11**, managed entirely with **`uv`**. See the root `CLAUDE.md` for
architecture, branching, and the deploy story.

## Commands (uv only — never bare `python`/`pip`)

```bash
uv sync --extra dev                                  # install/lock deps (+ ruff, pytest)
uv run uvicorn intel_platform.api.app:app --reload   # run API on :8000
uv run pytest                                         # tests (asyncio auto-mode)
uv run pytest tests/test_x.py::test_y -v              # one test
uv run ruff check .                                   # lint (line-length 120, py311)
uv run ruff format .                                  # format
```

`ruff` and `pytest` live in the `dev` optional-dependencies extra, so use
`uv sync --extra dev` (plain `uv sync` omits them). The Docker image installs
the spaCy model automatically; for the individual-dev path above, install it
once (it is not in the lock):

```bash
uv pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

Tests live in `backend/tests/` (`testpaths=["tests"]`, `asyncio_mode = "auto"` —
just write `async def test_...`, no decorator needed).

**`uv run pytest` needs a live Neo4j.** ~50 graph tests connect to
`bolt://localhost:7687` (`neo4j`/`changeme` — see `tests/conftest.py`); they
error, not skip, when it is down. Bring it up with `docker compose up neo4j`
(APOC is required — `graph/store.py` uses `apoc.create.relationship`) and
initialize the schema once against a fresh DB:

```bash
uv run python -c "from neo4j import GraphDatabase; from intel_platform.graph.schema import initialize_schema; d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','changeme')); initialize_schema(d); d.close()"
```

CI (`.github/workflows/ci.yml`) does exactly this — Neo4j+APOC service, schema
init, then `pytest` — so it is the canonical reference for a green run.

## Package map (`src/intel_platform/`)

| Package | Responsibility |
|---------|----------------|
| `api/` | FastAPI app + `routes/` (27 routers: auth, documents, entities, graph, collections, collection_plans, pirs, query, assess, analysis, topics, reports, geo, timeline, search, watchlist, personas, snapshots, admin_config, llm, ingest, export, notebook, projects, health, enrichment, attack). App = `api.app:app`; middleware = rate-limit / request-logging / security-headers. |
| `services/` | Business logic (22 + `attack/`): extraction, enrichment, ingestion, graph_builder, graph_rag, hybrid_retrieval, vector_search, document_clustering, topics, assessment, `requirement_assessor` (per-EEI gap analysis that drives re-tasking), analytic_agents, summarization, geocoding, collection_planner, plan_executor, reports, mindmap_export, graph_cache, text_utils, `content_quality` (one gate deciding whether a fetched page is content), `llm_output` (reading labelled values and JSON back out of model replies). `attack/` = MITRE ATT&CK® (`stix_parser` pure STIX→model, `graph_ops` Neo4j load + matrix/technique/resolve/navigator/attribution reads, `ingest` fetch-and-load, `embeddings` technique-catalog→pgvector, `mapping` RAG text→technique, `vuln_chain` CVE→ATT&CK chain: CWE/CAPEC XML fetch+parse → `(:Cwe)-[:ENABLES]->(:AttackTechnique)` reference edges + per-project `resolve_cve`, `d3fend` lazy keyless D3FEND countermeasure fetch + Postgres cache, `report` ATT&CK-structured intelligence product: graph sections + deterministic markdown + optional LLM narrative). |
| `collection/` | Agentic web collection: `search` (multi-engine via ddgs, see below) → `crawler`/`scraper` (crawl4ai) → `runner`/`executor` (CollectionRunner) → ingest. `tasks.py` = Celery. `agentic.py` = LLM-driven planning. `requirement_loop.py` = re-tasks collection at the EEIs the planned sources left unanswered (see "Collecting against a requirement"). |
| `llm/` | Multi-provider layer: `anthropic`, `openai_provider`, `cohere_provider`, `ollama`, plus `embeddings`, `skills`, the **`orchestrator`**, and **`providers`** (`_get_provider` / `_get_collection_provider` / `_get_extraction_provider` / `_resolve_api_key` / `_cloud_provider_from_env` — the single source of truth for provider selection; services import from here, not from `api/routes/llm.py`, which only re-exports them). |
| `enrichment/` | Cyber-observable enrichment: `observables` (refang/classify), `base` (provider ABC + registry), `cache` (Postgres cache + rate limiter), `service` (Investigate orchestrator), `hook` (auto-enrich), `providers/` (dns, geoip, kev, nvd, rdap, certs, email — keyless, egress via `ProxiedClient`). |
| `graph/` | Neo4j: `schema.py` (`initialize_schema`), `store.py`. |
| `db/` | Postgres (SQLAlchemy async): `engine.py` (`init_db`), `models.py`. |
| `models/` | Pydantic v2 domain: `entities`, `relationships`, `type_hierarchy`, `requests`, `responses`. |
| `connectors/`, `data/`, `mcp/` | External connectors, seed/data, and an MCP server surface. |

## Data stores

- **Neo4j** — the knowledge graph (entities + relationships). Schema is created
  at app startup (`graph.schema.initialize_schema`). Local: `bolt://localhost:7687`
  (`neo4j` / `changeme`). Access via `api.deps.get_neo4j_driver`.
- **Postgres + pgvector** — documents, embeddings, PIRs (`pirs` — the
  requirements spine, linked to the plans they drove via `collection_plans.pir_id`,
  with per-EEI collection state in `pir_requirements`)
  and collection-plan state. Async SQLAlchemy; tables initialized at startup via
  `db.engine.init_db()` (no Alembic migration flow yet — schema is created on
  boot). `create_all` never ALTERs an existing table, so a **new column on an
  existing table** must also be added to `_ADDITIVE_COLUMNS` in `db/engine.py`
  (idempotent `ADD COLUMN IF NOT EXISTS`) or deployments that already have the
  table will not get it.

## Collecting against a requirement

Collection is driven by the requirement, not just by the planner's source list.

- **`pir_requirements`** holds one row per EEI: `status` (pending/satisfied/unmet),
  `attempts`, `next_queries`, and the assessor's `assessment_missing` /
  `assessment_confidence`. `Pir.eeis` remains the source of truth for the
  criteria *text* — every existing consumer reads it — and these rows carry the
  state that text acquires. `sync_requirements()` keeps them aligned; re-wording
  an element resets its state, because a reworded element is a different
  question.
- **After the planned sources are collected**, `run_requirement_passes()` assesses
  each still-open element against what was actually gathered and turns the gap
  into the next search. Skipped entirely when a plan has no `pir_id`, so plans
  raised from free text behave as before.
- **Three stopping conditions, reported separately**: every element satisfied;
  an element retired after `attempts_per_element` (tried and given up on — not
  the same as untried); or the source/pass budget exhausted with elements still
  open. **An exhausted run is never reported as a satisfied one.**
- **`requirement_assessor.assess_requirement()`** returns `assessed=False` on a
  provider outage or an unparseable reply rather than an unsatisfied verdict. An
  outage is not evidence that an element is unanswered, and recording it as one
  would retire elements for infrastructure reasons.
- **Search tries several engines** (`SEARCH_BACKENDS`, default
  `auto,brave,bing,duckduckgo`). `ddgs` fronts engines that fail independently,
  and a single-engine search starves a run silently — it acquires nothing and
  still reports success.
- **`content_quality.rejection_reason()`** is the one place judging whether a
  fetched page is content, applied *before* it can spend a source from the
  budget, and it returns a reason so a blocked page is distinguishable from an
  empty one in the activity trail.
- **The active persona shapes decomposition**, via
  `collection_plans.refinement_system_prompt()`. Which elements a requirement is
  split into decides what gets collected, so that is where expertise applies.

## LLM providers

Provider-agnostic. Pick via config (`default_llm_provider`, `default_llm_model`;
`.env.example` ships Ollama + `qwen2.5:14b` for local, code default is
`anthropic`). **Always go through `llm/orchestrator.py`** — do not re-add
per-module provider selection. Embeddings default to OpenAI (1536-dim), also
Cohere/Ollama.

High-volume **collection** work (source resolution + per-doc summaries) can route
to a dedicated provider so it won't drain a rate-limited cloud key — see
`collection_llm_provider`/`collection_llm_model` (empty = default provider,
`ollama` = offload local) and `_get_collection_provider` in `llm/providers.py`.

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
