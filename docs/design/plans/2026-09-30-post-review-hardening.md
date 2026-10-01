# Post-Review Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. One worker per package in its own git worktree with its own databases; the lead integrates serially onto `feat/post-review-hardening`, then runs two sequential post-merge packages, then the e2e pass.

**Goal:** Execute the open items and the eight structural adjustments recorded after the 2026-09-30 review: durable collection jobs on a separate worker, a pinned egress proxy for Chromium, Alembic migrations, countable degraded outcomes, document-mention edges with one evidence endpoint, generated API client types, a corpus-backed extraction eval and the quality fixes it drives, Next 15, cookie sessions, the file splits, the per-run test prefix, and the small leftovers.

**Architecture:** Five parallel packages by file ownership (P platform, G graph, W worker+egress, X extraction eval, F frontend), then two sequential post-merge packages (T test prefix, S file splits). Contracts below are fixed up front; each side implements against them without waiting.

**Spec:** `docs/code-review-2026-09-30.md` ("Remediation status" and the adjustment list in the 2026-09-30 session), plus this document.

## Global constraints

- Branch from `feat/post-review-hardening`; never commit to `main`.
- Definition of done is unchanged (backend `ruff` + full `pytest`; frontend `lint` + `build` + `test`). Backend packages that need Postgres start their own pgvector container (ports below).
- LLM provider selection stays in `llm/providers.py`; model output is read only through `services/llm_output.py`.
- Every new setting goes in `Settings` and `.env.example` (P owns both; others read with `getattr(settings, name, default)` and list the setting in their report).
- No behaviour change in a split or a type-generation step: those packages must leave every existing test passing without editing the test's assertions.
- Billed model calls happen only in the explicit eval runner (`@pytest.mark.eval`, excluded by default), never in the unit suite. The Cohere key in the repo-root `.env` may be used for eval runs.
- Commit trailer on every commit:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01XmtRBmBBfAoEphDqi3e1MX`

## Review focus (inputs no package's happy path exercises; each owner adds the test)

1. A worker that dies mid-run with the job row still `running`: `current_run_state` must report `stalled` once the heartbeat is older than the stall window, and `/execute` must then allow a new run. (W)
2. A CONNECT request for a host whose first resolution is public and second is private: the egress proxy must connect to the IP it vetted, never re-resolve. (W)
3. An Alembic upgrade on a database that `create_all` already populated at the old schema (the Railway case): `alembic upgrade head` must be a no-op apart from stamping, not a failure. (P)
4. A cookie session request without the custom header on a state-changing route: 403, so a cross-site form post cannot act as the analyst. (P, F e2e)
5. An entity created concurrently by two builds with the same normalised name: exactly one node afterwards. (G)

---

## Packages and ownership

| WP | Name | Neo4j | Postgres | Owns |
|---|---|---|---|---|
| P | platform | 7688 | 5436 | `backend/alembic/**` (new), `backend/alembic.ini` (new), `db/{engine,models}.py`, `api/{auth,deps}.py`, `api/routes/{auth,health,admin_config,personas,reports,ingest,assess}.py`, `services/{telemetry(new),vector_search,topics}.py`, `enrichment/service.py`, `services/attack/mapping.py`, `config.py`, `.env.example`, `backend/scripts/export_openapi.py` (new), `backend/CLAUDE.md` (migrations + telemetry sections), `SECURITY.md` (session cookie) |
| G | graph | 7689 | – | `graph/**`, `services/{graph_builder,graph_rag,hybrid_retrieval}.py`, `api/routes/{entities,documents}.py`, `models/entities.py` |
| W | worker-egress | 7690 | 5437 | `collection/**`, `db/jobs.py` (new), `intel_platform/worker.py` (new), `api/routes/collection_plans.py`, `services/plan_executor.py`, `start.sh`, `Dockerfile`, `backend/Dockerfile`, `docker-compose*.yml`, `.github/workflows/ci.yml`, `backend/CLAUDE.md` ("Is a run in flight?" section only) |
| X | extraction-eval | 7691 | – | `services/{extraction,text_utils,content_quality}.py`, `llm/skills/**`, `data/relationship_types.yaml`, `tests/eval/**`, `tests/fixtures/extraction*/**`, `backend/scripts/build_eval_corpus.py` (new), `backend/pyproject.toml` (the `eval` marker only) |
| F | frontend | – | – | `frontend/**`, `docs/screenshots/**` |
| T (post-merge) | test-prefix | 7689 | – | `backend/tests/**` |
| S (post-merge) | splits | 7689 | – | `api/routes/collection_plans.py`, `api/routes/pirs.py` and the new modules they split into; their tests |

## Cross-package contracts

1. **Telemetry (P → W, X, G).** `services/telemetry.py` exposes `record_degraded(subsystem: str, reason: str, *, detail: str = "") -> None` and `snapshot() -> dict[str, dict[str, int]]` (subsystem → reason → count since process start, plus `since`). `/health` gains `degraded: {subsystem: total}`; `GET /admin/degraded` (admin) returns the full snapshot. Subsystem names: `extraction`, `embeddings`, `enrichment`, `llm`, `topics`, `attack_mapping`, `collection`. W calls it for degraded extraction chunks and failed sources in `agentic.py`; X does not call it (extraction returns flags; callers record).
2. **Jobs table (W → P).** W creates `db/jobs.py` with `class CollectionJob(Base)` (`__tablename__ = "collection_jobs"`: `id` UUID, `plan_id`, `project_id`, `kind` (`agentic` | `requirements`), `status` (`queued|running|succeeded|failed|cancelled`), `worker_id`, `heartbeat_at`, `started_at`, `finished_at`, `error`, `created_at`). P adds `from intel_platform.db import jobs  # noqa: F401` to `db/models.py` so the table is in `Base.metadata`, and the lead regenerates the Alembic migration after W merges.
3. **Run state (W).** `collection_plans.current_run_state()` reads the job table: `running` while `status='running'` and `heartbeat_at` within `collection_stall_seconds` (default 120); `stalled` beyond it; `failed`/`completed` from the row; no row → `idle`. `plan_should_stop` also returns True when the job is `cancelled`. `_inflight_runs` and the in-memory tracker are removed.
4. **Worker mode (W).** `settings.collection_worker_mode` (`inline` default; `worker`). `inline` runs the loop as an asyncio task in the API process but still writes and heartbeats the job row; `worker` only enqueues and `python -m intel_platform.worker` executes. `start.sh` runs the worker as a third supervised process with mode `worker`; compose adds a `worker` service; CI's e2e stack includes it.
5. **Egress proxy (W).** `collection/egress_proxy.py` runs a local CONNECT/HTTP forward proxy on `127.0.0.1:<ephemeral>`: resolves once through `url_guard`, rejects non-public, connects to the vetted IP, tunnels; when an upstream Tor/VPN proxy is configured it chains to it instead of resolving. The crawler passes it to Chromium as `--proxy-server`. `settings.egress_proxy_enabled` (default True).
6. **Mentions (G → F).** `graph_builder` writes `(:Document)-[:MENTIONS {count, first_seen}]->(:Entity)` for every entity in a document; `schema.ensure_mentions_edges(driver)` backfills from `source_doc_ids` at startup. New `GET /entities/{id}/documents?limit=&offset=` returns `{documents: [{id, name, url, source_doc_id, mention_count, passages: [{text, offset}]}], count, total}` with up to 3 evidence passages per document. `GET /documents/{id}` lists entities via MENTIONS. GraphRAG and hybrid retrieval read MENTIONS.
7. **Entity uniqueness (G).** `models/entities.py` gains `normalized_name` (lower, whitespace-collapsed, punctuation-trimmed); `schema.py` adds a uniqueness constraint on `(project_id, normalized_name, entity_type)` for `:Entity`; `create_entity` becomes a single `MERGE` on that key. Backfill of `normalized_name` runs in `initialize_schema`; a duplicate pair found during backfill is merged (direction-preserving, as the merge route does) and logged.
8. **Session cookie (P → F).** `POST /api/auth/login` sets `sentinel_session` (httpOnly, SameSite=Lax, Secure when `settings.session_cookie_secure`, path `/`) and still returns the JSON body minus `access_token` (F stops storing it). `get_current_user` accepts the cookie or a bearer token. Cookie-authenticated **state-changing** requests (non-GET/HEAD/OPTIONS) require header `X-Requested-With: sentinel` or get 403. `POST /api/auth/logout` clears the cookie. `GET /api/auth/me` returns `{username, role}`. API-key callers are unaffected.
9. **OpenAPI export (P → F).** `backend/scripts/export_openapi.py` writes `backend/openapi.json` (deterministic key order). F runs `openapi-typescript` over it into `frontend/src/lib/api.generated.ts` via `npm run gen:api`, and a vitest asserts the committed file matches a fresh generation (so drift fails the frontend job).
10. **Degraded card (P → F).** F's admin page renders `/admin/degraded` as a card: one row per subsystem with the total and the top reasons.
11. **Settings (P).** `collection_worker_mode="inline"`, `collection_stall_seconds=120`, `egress_proxy_enabled=True`, `session_cookie_name="sentinel_session"`, `session_cookie_secure=False`, `session_cookie_max_age=86400`.

## Package task lists

### WP-P platform
1. **Alembic.** Scaffold `backend/alembic` with an async `env.py` reading `settings.postgres_url`; baseline migration autogenerated from the current models (including pgvector columns at `settings.embedding_dimensions`); `init_db` runs `alembic upgrade head` instead of `create_all` + `_ADDITIVE_COLUMNS` (keep `_DATA_REPAIRS` and the vector-width check). On a database that already has the tables but no `alembic_version` (every existing deployment), detect it and `alembic stamp head` first (review focus 3). Tests run against your Postgres on 5436: empty DB → upgrade; pre-populated-by-`create_all` DB → stamp then no-op; `alembic check` clean. Document the flow in `backend/CLAUDE.md` (replace the `_ADDITIVE_COLUMNS` paragraph).
2. **Telemetry** (contract 1) and the call sites you own: `vector_search` (embedding failures, width mismatch), `enrichment/service.py` (provider errors), `attack/mapping.py` (unparsed), `topics.py` (label failures, summary errors), `reports.py`/`assess.py` (LLM 503s), `ingest.py` (degraded chunks from `ExtractionResult.degraded`).
3. **Persistence.** Personas (custom ones and the active selection) and the admin LLM override move to `AppSetting` rows; `get_llm_override()` reads the row. Built-in persona ids still cannot be overwritten.
4. **`GET /reports/{id}`** scoped to `entity_type='Report'` and the project; 404 otherwise.
5. **Ingest naming.** `POST /ingest` accepts an optional `source_name` form field for text content; default stays `text_input`.
6. **Session cookie** (contract 8), with tests for cookie login, bearer still working, missing header → 403 (review focus 4), logout, `/me`. SECURITY.md paragraph.
7. **OpenAPI export** (contract 9) and `db/models.py` import line (contract 2), settings (contract 11).

### WP-G graph
Contract 6 (edges, backfill, endpoint, document entities, GraphRAG/hybrid), contract 7 (normalised name, constraint, single-statement MERGE, backfill-merge, concurrency test with two threads building the same entity: review focus 5). Keep `source_doc_ids` written for one release. Evidence passages reuse the extraction in `documents.py`'s evidence route (move it to a shared helper you own).

### WP-W worker-egress
Contracts 2, 3, 4, 5; review focus 1 and 2. `python -m intel_platform.worker`: polls `collection_jobs` with `FOR UPDATE SKIP LOCKED`, sets `worker_id`, heartbeats every 10 s in a background task, runs the agentic loop and requirement passes, writes terminal status and a sanitised `error`. `/execute` inserts the job (202 with `job_id`) and, in `inline` mode, also starts the task. `plan_should_stop` honours `cancelled`; a new `POST /collection-plans/{id}/cancel` sets it. The legacy `/collections` runner also writes job rows. Compose, CI e2e stack, `start.sh` (three processes; exit non-zero if any dies), root `Dockerfile` unchanged apart from the entrypoint already being `start.sh`. Egress proxy with a fake resolver test for the rebinding case and a test that a Tor/VPN upstream is chained rather than resolved locally. Telemetry calls in `agentic.py` (contract 1). Update the "Is a run in flight?" section of `backend/CLAUDE.md`.

### WP-X extraction-eval
1. **Corpus.** `backend/scripts/build_eval_corpus.py` scrolls the local Qdrant at `http://127.0.0.1:6333`, collection `kestrel` (334 points; payload keys `text`, `title`, `doc_id`, `chunk_id`), and `openrep` for variety. Select about 40 chunks whose text contains an "Entities identified in this reporting:" line; that line is the seed of the gold set. **Strip every classification and releasability marking** (`NS`, `NATO SECRET`, `REL-NATO`, `(NS)` paragraph markers and the like) from the stored text; keep the `EXERCISE — FICTIONAL` banner; this repo is public. Write `tests/fixtures/extraction_corpus/<chunk_id>.txt` and `_expected.json` in the existing fixture format, with types assigned from the names (vessels and hull numbers → `Vehicle`/`Hardware` per the type hierarchy, units → `Organization`, places → `Location`, people → `Person`) and relationships where the sentence states one. Review each expected file by reading the text; the seed line is a starting point, not the answer.
2. **Runner.** Extend `tests/eval` with `run_corpus_eval.py --mode nlp|llm|hybrid` producing `corpus_eval_<mode>.json` (precision/recall/F1 overall and per type, plus relationship metrics) and a markdown summary. `@pytest.mark.eval` tests wrap it and are excluded by default (`addopts = -m "not eval"` in `pyproject.toml`). Run all three modes once with the real Cohere key and commit the results.
3. **Quality fixes, driven by the numbers.** Known from the live run: "Windows" typed `Location`, "Netgear ProSAFE" typed `Organization`, five of six relationships dropped as `ASSOCIATED_WITH`, a `USES`/`EXPLOITS` edge to a CVE not created. Fix the type canon and the NLP label mapping (software/product/hardware lists), the relationship-drop rule (keep a typed edge when the sentence states it; drop only the generic fallback), and the CVE edge. Re-run the eval after each fix; every fix must move a number. Record before/after in `tests/eval/README.md`.

### WP-F frontend (sequential, in this order)
1. **Next 15 + React 19.** `next@15`, `react@19`, `react-dom@19`, `@types/react*@19`, `eslint-config-next@15`; async `params`/`searchParams` in the six files that use them; RTL/vitest compatibility; `next.config.mjs` keys; keep the CSP. Lint, build, unit tests green; run `npm audit --omit=dev` before/after and report.
2. **Generated types** (contract 9): `npm run gen:api`, `api.generated.ts` committed, every `api.ts` function's response typed from it, the drift test, and fix any mismatch the types reveal (list them).
3. **Cookie session** (contract 8): drop `auth_token` from storage; `withCredentials`; `X-Requested-With: sentinel` on every request; login redirects after the cookie is set; `auth_user`/`auth_role` come from `/api/auth/me` on load; logout calls the endpoint; e2e `global-setup.ts` logs in through the API and persists the cookie in `storageState`.
4. **Evidence chain** via `GET /entities/{id}/documents` (contract 6), replacing the per-document loop on the network page; document page entities unchanged in shape.
5. **Split `app/network/page.tsx`** into `app/network/` components and hooks (graph canvas, entity panel, filters, snapshots, AI actions) with no behaviour change; unit tests still pass; lint clean.
6. **Degraded card** (contract 10) on the admin page.
7. **Default basemap** to OpenStreetMap (CARTO now watermarks); CSP hosts updated.
8. **Hero PNG** regenerated from `docs/screenshots/hero.html` with Playwright.

### WP-T test-prefix (after all merges)
`conftest.py` defines `TEST_RUN = f"test-{uuid4().hex[:8]}"` and a `tp(name) -> str` helper; the teardown deletes only `project_id STARTS WITH $prefix`. Rewrite every `project_id="test-..."` literal in `backend/tests/**` to `tp("...")` (mechanical; no assertion changes). Document in `backend/CLAUDE.md` that two suites may now share a Neo4j.

### WP-S splits (after T)
`api/routes/collection_plans.py` → `routes/collection_plans/{plans,execution,uploads,refinement}.py` + `services/plan_runs.py`; `api/routes/pirs.py` → `routes/pirs/{crud,assess,requirements}.py` + `services/pir_judge.py`. Router prefixes and paths unchanged (OpenAPI diff must be empty against `backend/openapi.json`); tests moved alongside; no behaviour change.

## Integration order (lead)

P → G → W (regenerate the Alembic migration for `collection_jobs`) → X → F; full checks after each. Then T, then S, sequentially. Then the e2e pass (Playwright plus the manual flows: cookie login, worker-executed collection run with cancel, evidence chain, degraded card). Then merge to `main` and push; no Railway deploy.

## Deferred (decided up front)
- Multi-user project ownership (ACLs): out of scope; noted for the showcase.
- GitHub repository settings and Railway variables: the owner's.
