# Agentic Collection — "Best of Both" Design

**Date:** 2026-05-27
**Status:** Approved — corrected after critical review

## Revision (post critical-review)

A critical review against the live code found the redesigned **AcquireView is mis-wired**: `submitPir` calls the *legacy* `collectionsApi.create` (which only writes a Neo4j node and never runs anything), never calls `.execute` on either pipeline, and the Trace tab reads the legacy collection status rather than the agentic `CollectionActivity` stream. The superior agentic pipeline (`collection_plans.py` / `run_agentic_loop`) has a complete API (`from-pir`, `execute`, `execution-status`, `/activity`) and frontend client (`collectionPlansApi`) — but the UI doesn't drive it. Therefore a **frontend rewiring** work item is added (now item 2 below), and items 3–5 (formerly 2–4) land on the agentic path that the UI will then actually exercise. The legacy `/collections` run path is treated as deprecated (endpoints left for back-compat).

## Goal

Make the intelligence-platform's agentic collection pipeline actually run in the deployed (Railway) environment, then fold in the three execution strengths of the Quarry app so intel-platform strictly exceeds both: working headless crawling, bounded-concurrency throughput, granular live telemetry, and per-document analyst summaries.

## Background

intel-platform already has a more capable collection architecture than Quarry: a PIR-driven agentic loop (`backend/src/intel_platform/collection/agentic.py`) of RESOLVE → ACQUIRE → EVALUATE with multi-source connectors and Neo4j knowledge-graph output, plus a simpler linear `CollectionRunner` (`runner.py`). Quarry (`C:\Users\user\Claude\crawl4ai-quarry`) is a one-shot search→crawl→extract worker, but with better execution mechanics (bounded concurrency, rich live telemetry, per-doc structured summaries).

The pipeline does not work in production for one reason: **the deployed backend never installs the Chromium browser**, so crawl4ai cannot launch. The deployed backend service uses the combined root `Dockerfile` (which installs the crawl4ai *library* via `uv sync` but never runs `crawl4ai-setup`). A separate `backend/Dockerfile` does run `crawl4ai-setup` as root but is not the one Railway deploys.

## Scope (4 work items)

### 1. Foundation — make headless crawling work in the deployed backend (REQUIRED)

**Approach:** Point the Railway `backend` service at `backend/Dockerfile` (backend-only) instead of the combined root `Dockerfile`, and harden `backend/Dockerfile` so Chromium installs reliably.

- Set the `backend` service `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile`.
- Harden `backend/Dockerfile` (runs as root throughout — no unprivileged USER, so apt works):
  - Keep `RUN uv run crawl4ai-setup`.
  - Add belt-and-suspenders (the lesson from Quarry, where `crawl4ai-setup` silently failed to fetch the browser): explicitly run, as root, `uv run playwright install-deps chromium` (OS libs) and `uv run playwright install chromium` (browser binary).
- The backend service no longer bundles the frontend; this is fine — the `frontend` service serves the UI independently (`Dockerfile.frontend`).

**Files:** `backend/Dockerfile` (modify); Railway `backend` service variable `RAILWAY_DOCKERFILE_PATH`.

**Verify:** redeploy; backend `/health` 200; trigger a collection and confirm a page is crawled (Chromium launches, no "Executable doesn't exist" error).

### 2. Bounded-concurrency crawling in the agentic acquire path

**Problem:** `agentic.py::acquire_source` crawls multi-URL web sources **sequentially** with `await asyncio.sleep(1)` between each (`for url in config["urls"][:10]: ... await asyncio.sleep(1)`). Slow and serial.

**Approach:** Replace the sequential loop with bounded-concurrency execution modeled on Quarry's `crawl_urls_with_progress` — an `asyncio.Semaphore` (default 4) gating concurrent `connector.acquire(single_config)` calls via `asyncio.gather`. Preserve per-URL error isolation (one failed URL must not abort the source). Concurrency limit configurable via settings (`collection_crawl_concurrency`, default 4).

**Files:** `backend/src/intel_platform/collection/agentic.py` (`acquire_source`); `backend/src/intel_platform/config.py` (new setting).

**Verify:** a source with N URLs crawls concurrently (wall-clock ≈ slowest URL, not sum); a single failing URL still yields the others.

### 3. Granular live telemetry surfaced in the redesigned AcquireView "Trace" tab

**Problem:** `CollectionActivity` events are coarse (per-source: queued/collecting/succeeded). Quarry exposes per-URL status (fetching/done/error), word counts, and timestamped stage logs.

**Approach:** Emit finer-grained `CollectionActivity` rows during acquire using the **existing schema** (no migration): new `event` values within the 32-char limit — `url_fetching`, `url_fetched`, `url_failed` — with structured detail packed into the `message` text (url, title, word_count, error). The existing collections activity API/SSE that AcquireView's Trace tab already consumes will render them. No new DB column (init_db uses `create_all`, which does not ALTER existing tables, so a column add would not apply cleanly — avoid it).

**Files:** `backend/src/intel_platform/collection/agentic.py` (emit events in the concurrent acquire path); frontend `frontend/src/components/sentinel/views/AcquireView.tsx` (Trace tab renders the new event types — minor formatting only if needed).

**Verify:** running a collection shows per-URL fetching/done/failed lines with word counts in the Trace tab in near-real-time.

### 4. Per-document structured summaries

**Problem:** intel-platform extracts entities/relationships into the graph but produces no per-document analyst summary. Quarry's `extractor.py` produces clean JSON: summary, key_facts, topics, sentiment.

**Approach:** Add `backend/src/intel_platform/services/summarization.py` with `async def summarize_document(content: str, provider) -> dict | None` (mirrors Quarry's extractor: system+user prompt, temperature 0, content truncated to ~20k chars, robust JSON parse). Call it once per crawled doc in the acquire path (after content cleaning, before/alongside chunked entity extraction), using the same provider abstraction (`_get_agentic_provider`). Store the result JSON as a `summary_json` property on the Neo4j `Document` node. Surface it in the Documents view (and the document detail) in the frontend.

**Files:** `backend/src/intel_platform/services/summarization.py` (new); `backend/src/intel_platform/collection/agentic.py` (call it in acquire); `backend/src/intel_platform/models/entities.py` + graph store (add/persist `summary_json` on Document); `frontend/src/components/sentinel/views/DocumentsView.tsx` (render summary card).

**Verify:** a crawled doc has a `summary_json` with summary/key_facts/sentiment; it renders in the Documents view.

## Data flow (after changes)

PIR/plan → RESOLVE (LLM → source configs) → **ACQUIRE (bounded-concurrent crawl → clean → per-doc summary + chunked entity/rel extraction → Neo4j Document + graph; per-URL telemetry)** → EVALUATE (LLM sufficiency check → bounded follow-ups) → COMPLETE.

## Error handling

- Per-URL failures isolated (gather with return-per-task; failures logged as `url_failed`, others continue).
- Summarization failure is non-fatal: log and store no `summary_json`; entity extraction and graph build still proceed.
- Chromium launch failure surfaces as a clear source-level error in `CollectionActivity` (not a silent hang).

## Testing

- **Foundation:** deploy verification — backend `/health` 200; a real collection crawls ≥1 page successfully.
- **Concurrency:** unit/integration — N-URL source completes in ≈ max(per-URL) not sum; injected single-URL failure does not abort the source.
- **Telemetry:** integration — `url_fetching`/`url_fetched`/`url_failed` events emitted per URL with word counts.
- **Summaries:** unit — `summarize_document` returns valid dict for sample content and `None` on provider error; integration — crawled doc carries `summary_json`.

## Out of scope

- Quarry's SQLite/FTS browsable library (intel-platform already has a Documents view + search; full-text-search parity is a separate, optional effort).
- New connector types beyond those already present (web/RSS/API/database/file).
- Changing the EVALUATE/follow-up agentic logic (it already exceeds Quarry).

## Risks / notes

- Adding Chromium + concurrent crawls increases backend runtime memory; may require a Railway plan with adequate RAM. Monitor after the foundation deploy.
- Cohere is the configured cloud provider (key set on the backend service); summaries and LLM extraction use it via `_get_agentic_provider`.
