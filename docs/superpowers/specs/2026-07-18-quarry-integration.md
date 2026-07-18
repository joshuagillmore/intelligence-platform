# Quarry Integration — Design Record

**Date:** 2026-07-18
**Status:** Implemented on `feat/quarry-integration`.
**Repo:** intelligence-platform

## Goal

Fold the useful ideas from **Quarry** (a high-volume collection/extraction tool)
into the platform's agentic collection pipeline, so large collection runs are
**fast**, **observable**, and **cheap** — without exhausting a rate-limited cloud
LLM key or losing the analyst-facing per-document summaries Quarry produced.

## Context that shaped the design

- **Cloud keys are the bottleneck for collection.** Source resolution and
  per-document summarization are high-volume LLM work. Pointing them at the same
  rate-limited cloud key used for analyst products (reports, assessments) drained
  it. Collection needs a provider it can hammer.
- **Sequential fetching was slow.** The acquire phase fetched a source's URLs one
  at a time with a `sleep(1)` between them — minutes of wall-clock for a handful
  of URLs, with no per-URL signal for the Trace view.
- **Quarry's per-doc summary card was worth keeping.** Analysts liked a fast read
  on each source (summary / key facts / topics / sentiment) without traversing
  the graph. The platform already has a provider abstraction to produce it.
- **Cohere's Command A+ returned empty answers.** The newer reasoning/MoE model
  "thinks" by default, and that reasoning shared — and crowded out — the visible
  output token budget, so the provider returned blank text.

## What landed (four pieces)

### 1. Hybrid collection provider routing

A dedicated LLM provider for high-volume collection work, so it doesn't compete
with the cloud key used for analyst-facing products.

- `api/routes/llm.py` `_get_collection_provider()` — returns a local **Ollama**
  provider when `collection_llm_provider == "ollama"` (using `collection_llm_model`,
  falling back to `qwen2.5:14b`); otherwise falls back to the **default provider**
  (`_get_provider()`), preserving prior behavior on deployments without a local
  Ollama. `collection_plans.py` passes this as `get_provider` into the agentic loop.
- `collection/agentic.py` `_get_agentic_provider()` — when a collection provider is
  explicitly configured it honors it **as-is** (it does *not* apply the usual
  Ollama→cloud upgrade, which exists elsewhere to get reliable JSON). With the
  setting empty, the prior logic stands: a cloud provider is used directly, and a
  configured Ollama is upgraded to a cloud key (cohere → anthropic → openai) when
  one is available, for structured-output reliability.
- Net effect: **empty config = unchanged behavior**; `ollama` offloads bulk
  resolution + summarization to the local model and keeps the cloud key for products.

### 2. Concurrent multi-URL fetch

`collection/agentic.py` `_acquire_urls_concurrent(...)` replaces the sequential
`sleep(1)` loop for `web_scrape` / `database` sources that resolve to a `urls` list.

- Network fetches run concurrently under an `asyncio.Semaphore` bounded by
  `collection_crawl_concurrency` (default 4).
- The shared async DB session is **not** concurrency-safe, so all writes to it are
  guarded by an `asyncio.Lock`; only the network I/O overlaps.
- Emits per-URL telemetry as `CollectionActivity` events —
  `url_fetching` / `url_fetched` / `url_failed` — which the Trace view renders.
- Fetches are capped at the first 10 URLs per source; returns `(records, errors)`
  and surfaces partial success (some URLs can fail without failing the source).

### 3. Per-document structured summarization

New `services/summarization.py` `summarize_document(content, provider)` produces
`{summary, key_facts, topics, sentiment}`, "mirroring Quarry's extractor" but
through the platform's provider abstraction (a single `generate` call, `temperature=0.0`,
best-effort JSON parse, output normalized with safe caps). Returns `None` on any
failure — it is strictly non-fatal to collection.

- Called per document during `acquire_source`; the JSON is stored on
  `Document.summary_json` in Neo4j (see `models/entities.py`).
- The documents route surfaces `summary_json` in both the list and detail responses.
- `frontend/src/app/documents/[id]/page.tsx` parses it defensively and renders an
  **AI Summary** card: sentiment badge, summary text, key-facts list, and topics.

### 4. Cohere Command A+

`llm/cohere_provider.py` now defaults to `command-a-plus-05-2026` and handles the
reasoning/MoE behavior:

- For models whose name contains `plus` or `reasoning`, it caps the thinking
  `token_budget` (1024) and **adds that budget on top of** `max_tokens` as headroom,
  so the visible answer still fits. (Fully disabling thinking returns a Cohere 500
  for this model, so capping — not disabling — is the fix.)
- Response assembly concatenates `.text` across **all** content items, skipping the
  reasoning-trace item. Previously it read a single item and returned empty answers.

## New config settings (`config.py`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `collection_crawl_concurrency` | `4` | Max concurrent URL fetches per source (piece 2). |
| `collection_llm_provider` | `""` | `""` = use the default provider (prior behavior); `"ollama"` = offload bulk collection locally (piece 1). |
| `collection_llm_model` | `""` | Model for the collection provider; falls back to `qwen2.5:14b` for Ollama. |

All three are `intel_platform.config.Settings` fields, so they are env-overridable
like any other setting.

## Follow-ups / not yet done

- **Summarization is inline and per-document** — one extra LLM call per acquired
  doc inside the acquire loop; no batching or caching yet. Offloading it to the
  collection provider (piece 1) keeps this off the cloud key but doesn't remove the
  per-doc cost.
- **`summary_json` is an opaque JSON string** on the Document node, not a typed or
  indexed field; the frontend parses it defensively. Fine for display, not for
  search/filtering on summary contents.
- **10-URL cap** per source in `_acquire_urls_concurrent` is a hard constant, not a
  setting.
- **Sentiment is free-text** normalized to a `neutral` default; the frontend maps
  only known values (positive / negative / neutral / mixed).
- Add the three new settings to `.env.example` (owned by the backend agent) so the
  config surface stays discoverable.
