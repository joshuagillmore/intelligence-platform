# Backend — `intel_platform`

FastAPI service: the collection → extraction → graph → analysis engine. Python
**3.11** (pinned in `.python-version`, which uv, CI and the images follow),
managed entirely with **`uv`**. See the root `CLAUDE.md` for architecture,
branching, and the deploy story.

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
yourself. It is not in the lock, so **every `uv sync` removes it again**:
reinstall after each sync (NLP extraction silently degrades without it):

```bash
uv pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

Tests live in `backend/tests/` (`testpaths=["tests"]`, `asyncio_mode = "auto"` —
just write `async def test_...`, no decorator needed).

**`uv run pytest` needs a live Neo4j, and exclusive use of it.** ~50 graph tests
connect to `bolt://localhost:7687` (`neo4j`/`changeme` — see `tests/conftest.py`);
they error, not skip, when it is down. The teardown runs
`MATCH (n) WHERE n.project_id STARTS WITH 'test-' DETACH DELETE n`, which deletes
**every** test project, not just the one the test made — so two pytest processes
against the same database delete each other's fixtures mid-test and fail in
unrelated files. A "flaky" graph or route test is nearly always this: check
whether another run (or CI against the same instance) is in flight before
chasing it. Bring it up with `docker compose up neo4j`
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
| `services/` | Business logic (22 + `attack/`): extraction, enrichment, ingestion, graph_builder, graph_rag, hybrid_retrieval, vector_search, document_clustering, topics, assessment, `requirement_assessor` (per-EEI gap analysis that drives re-tasking), analytic_agents, summarization, geocoding, `geo/` (`coordinates`: MGRS/DMS/decimal parsing and conversion via pygeodesy; `overpass`: OSM local-feature lookup through `ProxiedClient`), collection_planner, plan_executor, reports, mindmap_export, graph_cache, text_utils, `content_quality` (one gate deciding whether a fetched page is content), `llm_output` (reading labelled values and JSON back out of model replies). `attack/` = MITRE ATT&CK® (`stix_parser` pure STIX→model, `graph_ops` Neo4j load + matrix/technique/resolve/navigator/attribution reads, `ingest` fetch-and-load, `embeddings` technique-catalog→pgvector, `mapping` RAG text→technique, `vuln_chain` CVE→ATT&CK chain: CWE/CAPEC XML fetch+parse → `(:Cwe)-[:ENABLES]->(:AttackTechnique)` reference edges + per-project `resolve_cve`, `d3fend` lazy keyless D3FEND countermeasure fetch + Postgres cache, `report` ATT&CK-structured intelligence product: graph sections + deterministic markdown + optional LLM narrative). |
| `collection/` | Agentic web collection: `search` (multi-engine via ddgs, see below) → `crawler`/`scraper` (crawl4ai) → `runner`/`executor` (CollectionRunner) → ingest. `agentic.py` = LLM-driven planning; its runs are asyncio tasks in the API process (no Celery/Redis). `requirement_loop.py` = re-tasks collection at the EEIs the planned sources left unanswered (see "Collecting against a requirement"). |
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
  and collection-plan state. Async SQLAlchemy; the schema is owned by **Alembic**
  and migrated at startup by `db.engine.init_db()` — see "Postgres schema
  migrations" below.

## Postgres schema migrations

The schema lives in `backend/alembic/versions/`; `backend/alembic.ini` and
`alembic/env.py` read the URL from `Settings.postgres_url` (never from the ini).
`init_db()` runs `alembic upgrade head` on every boot, inside one transaction
holding a Postgres advisory lock, so the API and the collection worker can boot
against one database at once.

**Changing the schema** = change the model in `db/models.py`, then a revision:

```bash
uv run alembic revision --autogenerate -m "add foo to bar"   # needs POSTGRES_URL at head
# read the generated file line by line: pgvector columns must be
# Vector(get_settings().embedding_dimensions) (autogenerate writes the literal
# width and an unimported pgvector.sqlalchemy.vector.VECTOR), and check indexes
uv run alembic upgrade head
uv run alembic check          # "No new upgrade operations detected." = models and migrations agree
```

Never edit `0001_baseline.py` or add a table to it; a new table is a new
revision. `tests/test_alembic_migrations.py` runs `alembic check` against a fresh
database, so a model change without a revision fails the suite (with a Postgres
exported; it skips without one).

**Existing deployments (adoption).** Every database created before Alembic has
the tables but no `alembic_version`. `init_db` detects that and, before
upgrading, replays the old bootstrap's last step — creates any baseline table
still missing, re-runs the frozen `_LEGACY_ADDITIVE_COLUMNS` — then
`alembic stamp 0001` (the baseline, not head), so later revisions still run.
For a database from the last pre-Alembic build the whole thing is a stamp.
To do it by hand instead of letting the app boot:

```bash
cd backend
uv run alembic current        # empty on a pre-Alembic database
uv run alembic stamp 0001     # only on a database create_all built at the current build
uv run alembic upgrade head
uv run alembic check
```

**Without pgvector** the baseline leaves out `chunk_embeddings` and
`attack_technique_embeddings` and the app runs graph-only; once the extension
is installed, the next boot creates them. The migrations ship in the images
next to `src/` (`/app/alembic`, `/app/alembic.ini`); `init_db` refuses to start
without them rather than run with an unmigrated schema.

## Degraded outcomes (telemetry)

A degraded outcome is work that completed worse than asked: an NLP-fallback
chunk, a document stored without embeddings, an enrichment provider error, a
keyword topic label, an unreadable ATT&CK mapping reply, a product that 503'd
on the LLM. Logging them was not enough to notice a quiet provider outage, so
they are also **counted**: `services/telemetry.py`.

- `record_degraded(subsystem, reason, *, detail="")` — call it where the
  degradation is decided, next to the existing log line. `reason` is counted,
  so keep it a short fixed vocabulary (`embed_failed`, `rdap: http 503`, an
  exception *type*), never an id or an exception message; `detail` goes to the
  log only. It never raises.
- Subsystems: `extraction`, `embeddings`, `enrichment`, `llm`, `topics`,
  `attack_mapping`, `collection`. Extraction itself does not record — it returns
  `ExtractionResult.degraded`/`reason`, and the caller (ingest, the agentic
  loop) records it.
- `snapshot()` → `{"since": iso8601, subsystem: {reason: count}}`, served at
  `GET /api/admin/degraded` (admin); `/health` carries `degraded: {subsystem: total}`.
- Counts are in-process and reset on restart; the collection worker process
  keeps its own and they do not reach the API's endpoints.

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

### "Is a run in flight?"

Never answer this from `CollectionPlan.status`. That is a lifecycle flag an
analyst sets by hand, and reading liveness off it is what made **Activate** lock
a plan out of execution: execution itself sets `ACTIVE`, so the old guard
(`DRAFT`/`PAUSED` only) stranded every activated plan and every plan whose run
died. Use `collection_plans.current_run_state()`, which both the execute guard
and `/execution-status` go through so they cannot disagree. It reports
`idle | running | stalled | completed | failed`, and only `running` blocks a new
run (409); `ARCHIVED` is refused separately.

It answers by looking, in this order:

1. `_inflight_runs` — agentic runs are `asyncio` tasks in the API process, so
   the task itself is the evidence. `register_run()` also holds the strong
   reference `asyncio.create_task` does not: a garbage-collected task cancels a
   live collection.
2. `plan_executor`'s in-memory tracker, for the synchronous path.
3. The `CollectionActivity` trail. Activity older than `_PROCESS_STARTED_AT`
   belongs to a run a restart killed, so it reports `stalled` immediately rather
   than waiting out `_STALL_AFTER_SECONDS`.

`stalled` deliberately does **not** block: past that point the previous attempt
is presumed dead, and refusing forever is the trap the flag-based guard set.
Progress counts come from `current_run_events()` — the trail holds every run a
plan has ever had, and summing all of them reported the last run's results on a
fresh one.

## LLM providers

Provider-agnostic. Pick via config (`default_llm_provider`, `default_llm_model`;
`.env.example` ships Ollama + `qwen2.5:14b` for local, code default is
`anthropic`). **Always go through `llm/orchestrator.py`** — do not re-add
per-module provider selection.

**Embeddings**: OpenAI (1536), Cohere (1024) or Ollama `nomic-embed-text` (768).
`EMBEDDING_DIMENSIONS` must match the provider you pick — both pgvector columns
and `vector_search`'s width guard read it, so a mismatch is rejected rather than
stored wrong. The value is applied when the baseline migration creates the
tables, and no migration resizes them: changing it on an existing database
means dropping `chunk_embeddings` and `attack_technique_embeddings` (the next
boot recreates them at the new width; their vectors need re-embedding under the
new provider anyway).

High-volume **collection** work (source resolution + per-doc summaries) can route
to a dedicated provider so it won't drain a rate-limited cloud key — see
`collection_llm_provider`/`collection_llm_model` (empty = default provider,
`ollama` = offload local) and `_get_collection_provider` in `llm/providers.py`.

## Conventions

- **Async handlers, sync Neo4j.** FastAPI + async SQLAlchemy + async httpx,
  but the Neo4j driver (and spaCy, PDF/xlsx parsing) is synchronous: from an
  `async def`, call it through `asyncio.to_thread`, never directly on the loop.
- **Pydantic v2** models for all request/response shapes (`models/`).
- Config only via `intel_platform.config.Settings` (pydantic-settings) — never
  read `os.environ` ad hoc in business logic.
- Don't leak internal error detail to API clients (past review finding);
  log server-side, return clean errors.
- The SSRF guard is `collection/url_guard.py`, not any one fetcher. `scraper`,
  `crawler` and `proxy` call it, so it cannot be bypassed by reaching for a
  lower-level fetch helper — keep it that way, and route any new outbound
  fetch through it.

## Definition of done

`uv run pytest` green **and** `uv run ruff check .` clean. No exceptions.
