# Code Review Report — Intelligence Platform

**Date:** 2026-09-30
**Reviewed at:** `71d3919a` on `fix/observables-and-topic-labels` (clean tree)
**Method:** Eight parallel read-only Claude Opus 5.5 reviewers, one per area,
consolidated by Claude Fable 5.1. Sixteen of the highest-impact claims were
independently re-verified against the code or by running the parser in
question; every one held. Reviewers did not modify files and did not run
`pytest` (it needs exclusive Neo4j). Previous full review:
`code-review-2026-03-22.md`.

**Scope:** all of `backend/src/intel_platform` (12 packages, ~25k lines),
all of `frontend/src` (~20k lines), Dockerfile/compose/Railway/CI, lockfiles,
`.env.example`, and a read of the test suite (124 files, 1,299 test functions).

## Remediation status (2026-09-30, branch `fix/code-review-2026-09-30`)

Every finding below was worked through the plan in
`docs/design/plans/2026-09-30-code-review-remediation.md` (nine packages, one
per file-ownership area, each TDD'd against the finding's failure scenario).
Unless listed here, a finding's status is **Fixed** on that branch.

| Finding | Status | Note |
|---|---|---|
| P-18 (backend half) | Not a bug | `/geo` already returned `edge_count`; a test now pins it. The UI half was the real defect and is fixed. |
| I-5 (Next.js) | Deferred | axios updated and `images.unoptimized` set; the Next 14 → 15 migration is a separate branch. Two `next`/bundled-postcss advisories remain until then. |
| I-6 (GitHub settings) | Reported | `.github/dependabot.yml` added. Private vulnerability reporting, secret scanning + push protection, Dependabot alerts/updates and a `main` protection rule are repository settings for the owner to enable. |
| P-5 | Mitigated | Evidence loop now runs 6-wide with a request token; a dedicated `GET /entities/{id}/documents` endpoint is still the right fix. |
| Low → A (personas) | Partial | Admin-only mutations and 409 on built-in ids are fixed; personas are still held in memory (root `CLAUDE.md` still says so). |
| Low → G (entity check-then-create race) | Deferred | The relationship upsert is now one locked MERGE; concurrent *entity* creation can still duplicate a node. |
| C-13 (URL dedupe) | Partial | Documents now record their `url`; URL-level dedupe needs a product decision (section pages change daily). |
| E-7 residual | Partial | Mapped TTPs are no longer re-sent; TTPs the model keeps rejecting still are, and more than 200 of them can starve later ones. |
| C-1/C-5 residual | Accepted risk | With Tor/VPN active, names resolve at the proxy (by design); in direct mode a rebinding host can be *read by page JavaScript* before the page is rejected, though it never becomes a Document. Closing that needs Chromium behind a pinned local proxy. |
| Low → R (`GET /reports/{id}`) | Open | Only `DELETE` was scoped to Report nodes in the project; `GET` still returns any node by id. |
| `/assess/generate` | Observation | Still makes a full extra LLM call via GraphRAG just to obtain context. |
| Railway environment | Operator task | `REQUIRE_SECURE_AUTH`, `JWT_SECRET`, `ENCRYPTION_KEY`, `MCP_ENABLED` and the admin password on the live instance were not verified from this repo. The managed Redis service there can be deleted. |
| `docs/screenshots/hero.png` | Stale | Its source no longer says "Celery"; the PNG needs regenerating. |

Verification on the integrated branch: backend `ruff` clean and the full suite
green against a dedicated Neo4j; frontend lint with zero warnings, vitest and
`next build` green; the production image builds with Chromium present.

**End-to-end run (local full stack, real Cohere model):** the Playwright suite
passed (24 tests, 8 guarded captures skipped), and the key flows were driven by
hand in Chrome: login; project select and dashboard (real centrality values);
network graph, entity panel with all source documents, true-direction
relationship and evidence chain; watchlist add → Watchlist page → sidebar
badge; Cyber, Timeline and Search totals; a Threat Assessment generated and
grounded; an assistant answer with sources; a streamed topic summary keeping
its structure; the status bar showing "Degraded" with Neo4j stopped. Two
defects that only a live run could show were found and fixed in the same
branch:

| Finding | Status | Note |
|---|---|---|
| Topic tree 500 after any watchlist add | Fixed | Watchlist nodes carry `project_id` but no entity `id`; label-less project scans returned them and `_build_entity_branches` died on `e["id"]`. Store scans now use `:Entity`; the builder skips id-less rows. Pre-existing since watchlists moved to Neo4j; masked until the watchlist UI worked. |
| Embedding width mismatch invisible | Fixed | pgvector columns are created at `EMBEDDING_DIMENSIONS` on first boot and never altered; a later provider switch (Cohere 1024 on a 1536 column) failed every insert with only a log line. `init_db` now compares live column widths with the setting and `/health` reports the mismatch with both remedies. |
| Text ingests named `text_input` | Open | `POST /ingest` with `content` ignores any supplied name; every pasted document is called `text_input`. Pre-existing; cosmetic but confusing in the evidence chain. |
Dependency advisories: backend 252 → 1 (a transitive nltk issue with no fix),
frontend production 6 → 2 (both the deferred Next line).

## Adjustments executed (2026-10-01, branch `feat/post-review-hardening`)

The open items and the eight structural adjustments proposed after the
remediation were executed per `docs/design/plans/2026-09-30-post-review-hardening.md`.

| Item | Status | Note |
|---|---|---|
| Next.js 14 → 15, React 19 | Done | No page needed code changes (all pages are client components). `npm audit --omit=dev` is now clean. |
| Collection off the API process | Done | `collection_jobs` table (Alembic revision), `python -m intel_platform.worker` claims with `SKIP LOCKED` and heartbeats; `start.sh` supervises three processes; compose and CI gain a `worker` service; run state is read from the job row; `POST /collection-plans/{id}/cancel`. Verified live: a queued run was claimed by the worker and cancelled mid-run. |
| Egress proxy for Chromium | Done | `collection/egress_proxy.py`: resolve once, connect to the vetted address, chain to Tor/VPN when configured; rebinding test in the suite. |
| Extraction quality + corpus eval | Done | Gold sets: `openrep-deep` (40 chunks, 510 entities, 73 relations; primary), `kestrel` (40), the three live-run cyber documents. Markings stripped; `@pytest.mark.eval` runs are opt-in. Hybrid gold edges found on openrep: 25 → 55 of 73; NLP typed F1 0.655 → 0.710; a scorer bug that matched any two equal-length names was fixed. |
| Generated API client types | Done | `backend/openapi.json` exported by script; `frontend/src/lib/api.generated.ts` via `npm run gen:api`; a drift test; six real mismatches fixed. Only 14 of 156 operations declare a response model, so most responses still rely on hand-written interfaces. |
| Alembic migrations | Done | Baseline `0001` plus `collection_jobs`; `init_db` runs `upgrade head` under an advisory lock; pre-Alembic databases are adopted by stamping the baseline. |
| Countable degraded outcomes | Done | `services/telemetry.py`; `/health.degraded`, `GET /admin/degraded`, an admin card; per-run counts on the job row. |
| Document MENTIONS edges + one evidence endpoint | Done | `GET /entities/{id}/documents` with passages; GraphRAG and hybrid retrieval read the edges; backfill at startup. |
| Entity uniqueness | Done | `normalized_name` with a uniqueness constraint and a single-statement MERGE; concurrent builds make one node. |
| Giant file splits | Done | `collection_plans` and `pirs` routes are packages; `services/plan_runs.py`, `services/pir_judge/`; the network page is 458 lines with 11 hooks and 18 components. OpenAPI diff empty. |
| Per-run test prefix | Done | Two full suites share one Neo4j (proved); a file lock covers the few tests that write project-less reference data. |
| Cookie sessions | Done | httpOnly `sentinel_session`, `X-Requested-With` CSRF header, `/me`, `/logout`; e2e spec. |
| Personas / LLM override persistence, `GET /reports/{id}` scope, text ingest naming, OSM basemap, hero PNG | Done | |
| Found during the final e2e | Fixed | A plan generated with no sources (model unavailable) executed as a clean zero; generation failures are now counted and a run with no requirement elements writes a trail event. The worker logged the status it asked for, not the cancelled one stored. |
| Still open | | Multi-user project ownership. |

## Follow-up round (2026-10-01, branch `feat/extraction-precision-and-response-models`)

| Item | Status | Note |
|---|---|---|
| Relationship precision | Done | Scoring now separates `typed` relations from generic associations and date links (which feed the timeline and stay). Generic associations are emitted only for a pair in one sentence with nothing typed between them; a model edge whose endpoint is not a listed entity is dropped and counted (`unlisted_endpoint`), so graph-build drops for unknown endpoints fell 75 → 4. Hybrid combined typed F1 0.244 → 0.277; llm 0.167 → 0.202. The prompt rules alone barely moved the model; the parser enforces them. |
| Government ↔ country | Done | `data/governments.yaml` (29 countries: name templates, forms such as "the Kremlin", capitals as metonyms) applied in every extraction mode and in graph resolution; a capital joins its country only when parsed as an actor. The largest typed-F1 gain in the model modes (llm 0.707 → 0.735). |
| NLP gaps | Done | Proper-name acronyms (JCPOA, NDAA, INDOPACOM) are extracted; heading fragments ("Assess Russian") are rejected by a heading-aware filter. |
| Response models on every operation | Done | 156 of 156 operations declare a model (was 14), proven by `tests/test_response_models.py` (84 tests comparing each declared response with the handler's value). Nine models are open-ended by design and say so. The stronger client types found one real UI bug (the network view's community mapping was always empty) and a dozen dead reads of fields no route sends. |
| Still open | | Typed relationship precision in the model modes is still low (0.13 to 0.17): the model names plausible edges the gold does not label. |

## Final round (2026-10-02, branch `feat/aliases-relations-and-project-access`)

| Item | Status | Note |
|---|---|---|
| Location aliases | Done | `Location.aliases`; the government↔country rule stores the written form ("the Kremlin", "PRC government", "Moscow" as actor) as an alias on the country node, merged as a set union; search and resolution match aliases; a name in the governments table is never resolved through an alias (so "talks in Moscow" stays a place). |
| IOC relation counts | Done | `GET /entities` items carry `relationship_count` (degree over analytic edges, Document mentions excluded); the cyber column shows it. |
| Project access control | Done | `project_members` (Alembic revision), roles owner/editor/viewer, admin bypass, open projects until the first owner is added, `require_project_access` on 121 of 159 operations with a fail-closed coverage test and an explicit allowlist; member routes; MCP tools apply the same rules through the request scope; the frontend shows roles, a members panel, and one shared no-access state. Verified live: non-member 403 (not 404), viewer refused a write through a form body, owner allowed, admin bypass, last-owner 409, project list filtered, MCP refusal. |
| Found on the way | Fixed | The source-acquisitions route never checked that the source belonged to the plan; `GET /collection-plans` and `GET /collections` without a project returned every project's rows. |
| Still open | | Typed relationship precision in the model modes. Projects created by an admin stay open until a member is added (by design; `SECURITY.md` says an admin should claim existing projects before analysts do). |

## Check results

| Check | Result |
|---|---|
| `backend: uv run ruff check .` | pass, 0 issues |
| `backend: uv lock --check` | pass |
| `backend: uv run pytest --collect-only` | 1,454 items collected, no errors (not executed) |
| Latest CI on `main` | backend 1,428 passed on CPython 3.11; e2e 31 passed, 1 skipped |
| `frontend: npm run lint` | pass, 4 `exhaustive-deps` warnings (findings F-15, F-16) |
| `frontend: npm run build` | pass, 19 routes; warns `serverExternalPackages` is not a Next 14 key |
| `frontend: npm run test` (vitest) | 174 passed |
| `frontend: npm audit --omit=dev` | 1 critical, 4 high, 1 moderate (next 14.2.35, axios 1.13.6) |
| `backend: pip-audit` on the lock | 141 advisories across 20 packages (pypdf 41, aiohttp 24, nltk 20, pyjwt 13, starlette 7) |
| Secrets grep, tracked tree + 937 commits | clean; only placeholders |
| GitHub repo security features | private vuln reporting, secret scanning, push protection, Dependabot all **off** |

## Executive summary

The platform is in better structural shape than at the March review: no
Cypher injection anywhere (dynamic labels and relationship types are all
allowlisted), no XSS sink in the frontend, no secrets in the tree or history,
error detail is mostly sanitised, and every outbound fetch from user, LLM,
search or feed input does go through the SSRF guard. Lint, build and CI are
green.

The problems are of a different kind. Reviewers found **175 findings (39
High, 80 Medium, 56 Low; ~150 after de-duplication)**, and the large majority
belong to the four silent-failure classes this repo has already named for
itself: success-shaped zeros, failures rendered as plausible values, flags
standing in for the thing, and model output parsed by the requested shape.
The suite's 1,428 passing tests catch none of them because the tests assert
the same assumptions as the code.

Seven findings should be fixed before anything else:

1. **The production image cannot crawl.** The root `Dockerfile` that Railway
   builds never installs Chromium (`crawl4ai-setup`); only the CI-tested
   `backend/Dockerfile` does. Every collection on the deployed instance fails,
   and the legacy runner records SUCCESS with zero documents.
2. **Headless-browser fetches follow redirects to internal hosts.** The guard
   checks the first URL only; Chromium follows a `302` to `127.0.0.1:8000`,
   `neo4j:7474` or the cloud metadata address and stores the response as a
   Document.
3. **An empty `JWT_SECRET` passes `REQUIRE_SECURE_AUTH` and lets anyone mint
   admin tokens**, and an already-seeded `admin/admin` is never re-checked.
   The flag guards the config, not the evidence.
4. **Relationship direction is discarded by `get_relationships`.** Entity
   merge reverses every incoming edge and silently drops ATT&CK edges;
   entity detail, snapshots and the cyber page all render edges backwards.
5. **Documents show zero entities everywhere.** The document routes count
   edges to Document nodes that no ingestion path ever creates; the link is
   the `source_doc_id` property.
6. **Hybrid extraction (the default) fuzzy-merges IOCs.** Adjacent IPs,
   CVEs and sub-techniques score above the 0.92 Jaro-Winkler threshold and
   collapse into one entity; one malformed LLM attribute aborts the whole
   document's graph build after a partial write.
7. **The requirement loop retires elements on provider outages.** Two failed
   assessments mark an element `unmet` permanently, contrary to
   `backend/CLAUDE.md`; the re-tasking search also ignores the configured
   Tor/VPN egress because an async call is never awaited.

## Findings

IDs: **A** API core/auth, **R** requirements/plans/assess, **C** collection,
**G** extraction/graph/db/llm, **E** enrichment/ATT&CK/MCP, **F** frontend
lib/components, **P** frontend pages, **I** infra/CI/tests. Confidence is
*Confirmed* unless marked. Paths are repo-relative.

### High

| ID | File | Finding |
|---|---|---|
| I-1 | `Dockerfile:27-33` | Production image never runs `crawl4ai-setup`/`playwright install`; `backend/Dockerfile:27` (used only by CI) does. Deployed crawling cannot launch Chromium. Runtime failure *Likely* (image not built here). |
| C-1 | `collection/crawler.py:70-114` | `crawl_urls` validates the initial URL only. crawl4ai follows 3xx and JS navigation; `result.redirected_url` is never re-checked, subresources unrestricted. Internal responses are stored as Documents. |
| A-3 | `api/auth.py:16-17`, `api/app.py:24,56` | `JWT_SECRET=` (present but blank) yields `""`; PyJWT signs/verifies HS256 with an empty key. `_IS_DEFAULT_SECRET` compares only against the literal default, so `REQUIRE_SECURE_AUTH` passes. A short `API_KEY` also authenticates as admin. |
| A-2 / I-3 | `api/auth.py:70-101`, `api/app.py:20-65`, `SECURITY.md:37-39` | Admin-password check runs only when zero users exist; boot warning reads the setting, not the stored hash. No change-password endpoint. A deploy that once booted admin/admin stays admin/admin under `REQUIRE_SECURE_AUTH=true`. README/SECURITY.md promise more than the code checks; no deploy file sets the flag. |
| A-1 | `api/middleware.py:21-27`, `api/auth.py:29-54` | Login throttle keyed on client IP. Without `TRUST_PROXY_HEADERS` every Railway client shares one IP (5 bad logins lock everyone out); with it, the leftmost `X-Forwarded-For` is client-supplied (unlimited brute force, unbounded `_failed_logins`). |
| A-5 | `api/routes/entities.py:83-113`, `graph/store.py:350-367` | `get_relationships` matches undirected and always reports `m` as target. Merge recreates every edge as `primary->other`; `create_relationship` raises on non-allowlisted types (MAPS_TO, HAS_WEAKNESS, ENABLES), swallowed before DETACH DELETE. Evidence, `source_doc_id`, polarity dropped; response says success. No merge test. |
| A-6 | `api/routes/documents.py:16,53-63` | Entity count/list read `(d)-[r]->(m)` edges; nothing creates a Document-endpoint edge (`graph_builder.py:430-456` sets `source_doc_id` only). Every document shows 0 entities. |
| A-7 | `graph/store.py:403-407` via `entities.py:57`, `query.py:78`, `graph_rag.py:86` | Subgraph and GraphRAG traverse shared ATT&CK/CWE catalog nodes into other projects' entities, then pull their documents into the LLM context. |
| A-4 / E-5 / P-note | `api/routes/graph.py:24-27`, `services/enrichment.py:39-45`, `services/graph_cache.py:41-55` | `/graph` caches its `limit`-truncated NetworkX graph (default 500) under the project key that centrality, communities, statistics, structural-holes and ego-network read expecting 10,000 nodes. Analytics depend on request order; `limit` is unbounded, so `/graph?limit=1` poisons every analytic for 300 s. Even the 10,000 build samples edges arbitrarily (`store.py:483-492` applies the same LIMIT with no ORDER BY) with no `truncated` flag. |
| G-1 | `services/extraction.py:1297-1322` | Hybrid `_match_llm` fuzzy-matches regex IOCs (JW ≥ 0.92) and appends kept NLP names to the comparison list. 185.220.101.42/.43/.44 (0.971), CVE-2024-3400/3401 (0.969), T1566.001/.002 (0.956) collapse to one entity. `graph_builder` refuses fuzzy matching for these types; hybrid does not. Reproduced. |
| G-2 | `services/graph_builder.py:434-446` | LLM `attributes` go straight into the Pydantic constructor; `"roles": "General"` raises `ValidationError` after earlier entities were committed and before any relationship. `/ingest` 500s with an orphaned Document; agentic marks the whole source failed. Reproduced. |
| G-3 | `llm/ollama.py:16-19,28-34` | No `raise_for_status()`, no `error` key check. A 404 "model not found" becomes `LLMResponse(content="")`. Since `_get_provider` always ends in an Ollama fallback, the "No LLM provider configured" branches in `llm.py:54`, `reports.py:259`, `topics.py:519`, `assess.py:130` are dead code; extraction silently drops to NLP, GraphRAG returns raw context labelled with the model name. No `num_ctx` (prompt truncation *Likely*). |
| G-4 / A-Med / R-Med / E-Med / C-Med | `graph/store.py:259-334`, `api/routes/ingest.py:30-102`, `collection/agentic.py:720,775`, `collection/runner.py:99`, `enrichment/service.py:82,186-262`, `api/routes/collection_plans.py:1041-1131`, `services/topics.py:27-92` | Sync Neo4j driver, spaCy, flat-file parsing, `web_search` (with `time.sleep`), `socket.getaddrinfo` and Louvain all run on the API event loop. Only `plan_executor.py:310` uses `to_thread`. `create_relationship` does ~4 label-less `MATCH (a {id:…})` scans per edge (no shared indexed label). One 40-edge document or one 10 MB upload stalls `/health` and every request. |
| C-2 | `collection/requirement_loop.py:280-283` | `get_active_proxy_config()` is async but not awaited; `.get_proxy_url()` on the coroutine raises, bare `except` sets `proxy=None`. Every re-tasking search egresses direct even in Tor mode. Tests stub it with a sync lambda. Reproduced. |
| C-3 | `collection/agentic.py:610-616`, `connectors/database.py:65-75` | Fan-out passes `{**config, "url": url}` per URL but `DatabaseConnector.acquire` reads the whole `urls` list each call: N URLs → N² fetches, N copies of each page, each counted as independent corroboration. Reproduced (5 → 25). |
| C-4 / R-2 | `collection/requirement_loop.py:192-218`, `services/requirement_assessor.py:139-181` | `assessment.assessed` is never read. Outage or unparseable reply increments `attempts`; at 2 the element becomes `unmet` and only `pending` rows are re-selected. Contradicts `backend/CLAUDE.md`. |
| R-1 / F-2 / P-7 | `services/topics.py:510,557-561`, `frontend/src/app/data-sources/page.tsx:240-253` | Summary streamed as 80-char slices in `data: {chunk}\n\n` with raw newlines inside; client keeps only lines starting `data: ` and never re-adds newlines. A 6-line summary arrives as `## Key Findingsps`; a cache hit delivers one line. Error path streams `str(e)` and caches it. |
| E-1 | `enrichment/service.py:151-184`, every `providers/*.py` catch block | Providers swallow transport/status/parse errors and return an empty `EnrichmentResult`; the service applies it, stamps `enriched: true`, caches for the full TTL (30 days geoip, 7 days NVD/email) and reports `status: "ok"`. Email outage writes `has_mx: false`. Reproduced. |
| F-1 | `frontend/src/components/Markdown.tsx:17-91` | No `img` override; react-markdown keeps https images. Scraped documents carry image markdown (crawl4ai default), `/query` returns raw context when the LLM fails, and there is no CSP. Zero-click fetch from adversary infrastructure bypasses Tor/VPN egress and leaks analyst IP and origin. |
| P-1 / R-Med | `frontend/src/app/products/page.tsx:265`, `api/routes/reports.py:257-286`, `api/routes/assess.py:129-186` | LLM failure returns 200 with `content: "Report generation failed…"`, `model: "none"`. Page shows "Report Ready", green "Grounded in N entities" badge, and lets it be saved, exported and printed with a classification marking. Network page renders `res.data.error` as the AI result. |
| P-2 / F-Low | `frontend/src/app/watchlist/page.tsx:31-40`, `app/page.tsx:85,553`, `app/network/page.tsx:967-969`, `components/Sidebar.tsx:99` | API returns `{watched_entities, count}`; four consumers read `entities`, `watchlist`, an array, or `.items`. Watchlist is always empty, badge always 0, "Remove from Watchlist" unreachable. |
| P-3 | `frontend/src/app/project/[id]/page.tsx:333`, `services/enrichment.py:55-58` | Centrality endpoint returns `degree`; page reads `e.centrality \|\| 0`. Every Key Entities row shows 0.000 / "Low". |
| P-4 | `frontend/src/app/network/page.tsx:289-306,526-544,1947` | `loadEntities` depends on `searchQuery`; mount effect depends on `loadEntities`. Each keystroke refires six endpoints, unmounts the d3 graph, and the `?select=` effect snaps the selection back. No debounce, no stale-response guard. |
| P-5 | `frontend/src/app/network/page.tsx:727-750` | `selectEntity` awaits `/documents/{id}/evidence` serially for up to 500 documents; no cancellation, so a slow run overwrites the next entity's evidence. |
| P-6 | `frontend/src/app/network/page.tsx:572-595,637-650` | Date brush is a no-op without another filter; with a confidence/rel filter, edges to brushed-out nodes reach `d3.forceLink` ("node not found", *Likely*), and there is no `error.tsx`. |
| P-8 | `frontend/src/app/cyber/page.tsx:136-228,548` | Each indicator type fetched at the server default of 50, `X-Total-Count` ignored; every tile (Critical, Enriched %, Attributed %) is computed over the truncated set beside a graph that says 412 nodes. |
| P-9 / R-Med | `frontend/src/app/timeline/page.tsx:21,157-191`, `api/routes/timeline.py:35,95`, `graph/store.py:199` | `/timeline` is `search_entities(limit=500)` ordered by name, then sorted by date; `count` is the truncated length. Type filter is a fixed list omitting TTP, Malware, Campaign, URL. Dashboard "Recent Activity" is the newest of an alphabetical slice. |
| I-2 | `.env.example:102` | `EMBEDDING_MODEL=                 # blank = …` parses (python-dotenv and compose) as the literal comment string. Verified. Anyone following the README quickstart gets a failing embedding model and silent graph-only retrieval. |
| I-4 | `backend/pyproject.toml:7,14,28,31` | `pypdf~=4.0` (41 advisories, infinite-loop/OOM class, fixed in 6.x) parsed synchronously in `/ingest`; `fastapi~=0.115` caps starlette at 0.46.2 (7); `mcp~=1.12`, `crawl4ai~=0.8.6` block fixes. `uv lock --upgrade` alone would clear pyjwt, python-multipart, aiohttp, cryptography, nltk, idna. |
| I-5 | `frontend/package.json:19,22` | Next 14.2.35 is an unsupported line with 23 advisories (2 critical Image Optimizer RCEs, App Router DoS, rewrite smuggling); `/_next/image` is anonymously reachable through the backend proxy. axios 1.13.6 has 32, cleared by `npm update`. |
| I-6 | `SECURITY.md:7-9`, no `.github/dependabot.yml` | Private vulnerability reporting (which SECURITY.md points to), secret scanning, push protection, and Dependabot are all disabled on the public repo. Confirmed via `gh api`. |

### Medium

**API core (A)**
- A-8 `api/routes/query.py:16`, `store.py:407`: `max_hops` unbounded and interpolated (int, not injectable); `/subgraph` at hops=5 through ATT&CK hubs enumerates paths with no LIMIT. Negative → Cypher syntax error → 500. Same at `mcp/server.py:18-24` (G-Med).
- A-9 `documents.py:100-128`: `entity_name=""` matches every index; a 10 MB doc builds ~10M passages.
- A-10 `ingest.py:30-102,122-132`: `/ingest/batch` writes files 1–2 then 400s on file 3; retry duplicates. No `max_document_chars` cap on the manual path.
- A-11 `store.py:354-366` → `entities.py:53`, `snapshots.py:113-125`: every edge reported outgoing (cyber page shows `1.2.3.4 → evil.com` for a RESOLVES_TO into the IP); snapshots double-count edges.
- A-12 `entities.py:141-146`: retyping changes `entity_type` only; Neo4j label and `entity_category` stay stale, so ATT&CK attribution and the map disagree with the panel.
- A-13 `projects.py:144-167`: project delete removes Neo4j only; `chunk_embeddings`, PIRs, plans, activity, catalog remain and `/search/semantic` still returns the deleted project's chunks.
- A-14 `export.py:120-123`: CSV formula injection from scraped entity names (`=HYPERLINK(...)`); frontend saves as `.csv`.
- A-15 / I-7 `crypto.py:11,40-56`: without `ENCRYPTION_KEY`, `encrypt` is identity (keys stored plaintext; SECURITY.md claims Fernet at rest); on `InvalidToken`, `decrypt` returns the ciphertext as the API key. `ENCRYPTION_KEY` and `CORS_ORIGINS` appear in no `.env.example` or doc.
- A-16 `admin_config.py:219-237`: activate-key deactivates by `req.provider` then activates `key_id` unchecked; a mismatched provider leaves two active keys and `scalar_one_or_none` raises on every LLM call.
- A-17 / I-8 `config.py:164`, `auth.py:16`, `app.py:17`: `JWT_SECRET`, `CORS_ORIGINS`, `ENCRYPTION_KEY` bypass Settings; `extra` defaults to forbid, so copying `.env.example` to `backend/.env` raises `extra_forbidden` (verified). The README "backend alone" path cannot start.
- A-18 / F-Low `notebook.py:21-58`: `note_type` echoed but never stored; list fetches 100 Reports then filters in Python; `linked_entities` counts requested ids, not successes.
- A-19 `documents.py:12-42`: silent `LIMIT 500` presented as total; `properties(d)` ships full content over Bolt to compute `content_length`.

**Requirements / plans / assess (R)**
- R-3 / C-Med `collection_plans.py:70-72,124-149`, `agentic.py:907-1146`: `run_agentic_loop` has no top-level handler; done-callback discards `task.exception()`. A crashed run reads "running" for 600 s, then "stalled", never "failed"; `/execute` returns 409 meanwhile. Harness-verified.
- R-4 `collection_plans.py:801-858`: execute guard is check-then-act across awaits; two POSTs start two loops; second task's registry entry is popped by the first's callback. Harness-verified.
- R-5 `services/llm_output.py:53` (+ duplicate `assess.py:24-45`): `(\d?\.\d+|[01](?:\.\d+)?)` matches the leading `1` of `15%`/`10`/`12.5%` → probability 1.0 → label "Unknown". Verified by running the parser. Fallback 0.5 is never flagged in the response.
- R-6 `pirs.py:474-481,1142,1213`: `_VERDICT_LINE` rejects table rows and bold fields; all-missing is reported as "the judging model returned no verdicts" and skips the retry.
- R-7 `collection_plans.py:221-265,604,675-678`: `_split_refinement` falls back to the first wordy line ("Here is a refined version…", "### 1. Assessment"); `refined_text` is written once (including on failure) and never corrected. Drives source resolution and the judge.
- R-8 `requirement_assessor.py:183-192`: `bool("false")` is True; a string `next_queries` iterates per character. Verified.
- R-9 `pirs.py:914-925,1048-1050`, `requirement_assessor.py:81-128`: injection screen is start-anchored but evidence is appended mid-line after ` :: `; the element assessor screens nothing, yet persists status and drives live searches.
- R-10 `pirs.py:999-1013`, `collection_plans.py:827-829`: `source_limit` persists in `routing_rules` across runs; assess compares an unordered plan's limit to succeeded sources summed across all plans ("9/3 sources").
- R-11 `pirs.py:1032`, `requirement_assessor.py:108`: PIR judge sees the first 600 entities by name; element assessor the first 60 by name regardless of element.
- R-12 `collection_plans.py:526-558`, `agentic.py:899,1126-1127`: PAUSED/ARCHIVED are never read by the loop; completion overwrites them with COMPLETED (un-archiving); provider failure also sets COMPLETED.
- R-13 `collection_plans.py:1115-1131`: `await file.read()` buffers the whole upload before the 50 MB check.

**Collection (C)**
- C-5 `url_guard.py:57-65`, `proxy.py:30-37`: guard resolves, then httpx/Chromium resolve again (TTL-0 rebinding); `socket.gaierror` is swallowed (fails open). Also resolves locally in Tor mode, leaking every target hostname to the local resolver (C-Med).
- C-6 `proxy.py:109-133`: `ProxiedClient` buffers unbounded bodies (feeds, api_feed, all enrichment providers).
- C-7 `connectors/flat_file.py:309-339`: read-only openpyxl pads rows to the declared `max_column` (16,384) before `MAX_COLUMNS` is checked; a ~1.5 KB xlsx with 100k one-cell rows allocates ~13 GB on the event loop. Reproduced.
- C-8 `requirement_loop.py:274-278`: dedupe reads `config["url"]` but planned sources store `config["urls"]`; built once from a detached plan.
- C-9 `agentic.py:1044-1066`: a follow-up failure flips an acquired source to "failed"; RSS follow-ups re-ingest the same feed up to 3×; follow-up URLs skip `_validate_urls`.
- C-10 `requirement_loop.py:344-354`, `agentic.py:626-658,820-829`: content-gate rejections still spend budget and log "collected: 1 record(s), 0 entities".
- C-11 `agentic.py:638-641`, `api_feed.py:100-111`: JSON API records without `content` are dropped uncounted ("Acquired 20 docs, 0 entities"); resolve prompt asks for `base_url` but the parser requires `urls`.
- C-12 `flat_file.py:442-460`: pretty-printed JSON object uploads are treated as JSONL; every line fails; success with 0 records. Reproduced.
- C-13 `agentic.py:713-719`: agentic Documents are built without `url=url` (runner path sets it). No provenance, no URL dedupe.
- C-14 `runner.py:33-95`, `collections.py:166-192`: legacy cancel is a no-op; liveness is the status flag (restart → 409 forever); SUCCESS written when every item errored.

**Extraction / graph / db / llm (G)**
- G-5 `extraction.py:1200-1278`: any LLM failure (429, timeout, one `"confidence": "high"`, list-shaped `data`) silently degrades the chunk to NLP with no marker; fence-split + `json.loads` instead of `json_object`; provider lookup outside the `try`.
- G-6 `graph_builder.py:351-352,457,473-474`: `name_to_id` keyed by cleaned names, relationship endpoints never cleaned; `**Yi Peng 3**` node stored, its edges dropped as "never extracted". Reproduced.
- G-7 `graph_builder.py:101-113`: substring fallback ignores `_types_compatible`; Person "Wagner" resolves into Organization "Wagner Group". Reproduced.
- G-8 / E-8 `ingestion.py:47,59`, `extraction.py:610,679-720`: chunk overlap cuts mid-token (`rs.com` minted as a Domain at 0.9); sourcing rule applies only to regex entities, not LLM-emitted Domain/URL; `_DEFANGED_TOKEN` records host only and misses `[:]`, `(dot)`, `{.}`, `(at)`, so `http://evil[.]com/gate.php` loses its URL.
- G-9 `vector_search.py:69-83`, `embeddings.py:124-144`: factory falls back across providers of different widths; no `len(vec)` guard on insert; a failing flush poisons the shared agentic session (`PendingRollbackError`) and the run's activity rows are lost. *Likely*.
- G-10 `document_clustering.py:631-658`: `k = min(max_k, n // level)` never deepens; every preset yields depth 2 (reproduced for n=20/60/200). Whole corpus embedded in one call (Cohere caps at 96, *Likely*); fallback to TF-IDF leaves no marker; `linkage` on the event loop.
- G-11 `graph_builder.py:380-433`: `source_doc_id` set only on create; merged entities never record later documents, so GraphRAG and hybrid RRF reach only the first.
- G-12 `extraction.py:900-903,1123-1157`: NLP relations look up unstripped `ent.text` after determiner stripping; subject binding by substring (`"it" in "Citrix"` → `Citrix TARGETS last week`). Reproduced.
- G-13 `store.py:278-307`: a contradicting source is appended to `corroboration_sources` before polarity is compared (denial counted as corroboration); only the first evidence sentence is kept.

**Enrichment / ATT&CK / MCP (E)**
- E-2 `routes/enrichment.py:35`, `hook.py:91`, `service.py:70`: a new `RateLimiter` per request, so provider quotas (ip-api 45/min, Nominatim 1/s) are never enforced across requests; throttled responses are then cached as empty (E-1).
- E-3 `providers/kev.py:68-70`, `nvd.py:90`: lookup by entity name; "Log4Shell" with `cve_id` set gets `known_exploited: false` cached.
- E-4 `service.py:82,186-262`: sync Neo4j on the loop (see G-4).
- E-6 `services/attack/mapping.py:101-125`: `_parse_matches` accepts only bare/fenced JSON; a prose lead-in → `[]` → counted as "skipped" → `{"mapped": 0, "skipped": N}` with no reason. `llm_output.json_object` parses the same reply. Verified.
- E-7 `mapping.py:42-54`: unresolved query excludes only `method: 'tcode'` edges, so LLM-mapped TTPs are re-selected every run; `LIMIT` with no ORDER BY, so TTPs past the cap are never reached; stale `llm` edges never removed.
- E-9 `api/app.py:104-109`, `mcp/server.py`: MCP mounts unauthenticated with graph-writing and LLM-spending tools; can be enabled under `REQUIRE_SECURE_AUTH=true`.

**Frontend lib / components (F)**
- F-3 `EnrichmentPanel.tsx:76-88,141`: cache miss returns every provider → null; panel labels each "cached".
- F-4 `EnrichmentPanel.tsx:61-116`, `network/page.tsx:2152`: not keyed by entity; state carries across; a finished run re-selects the previous entity.
- F-5 `StatusBar.tsx:12-16`, `Sidebar.tsx:72-78`, `health.py:97-102`: `/health` is 200 with `status: "degraded"` when Neo4j is down; both components treat 2xx as nominal. The unit test mocks a field the component never reads.
- F-6 `AttackMatrix.tsx:229-244,548-577`, `attack.py:136-144`: `/attack/embed` 200 `{embedded: 0, reason}` shown as "Embedded 0 techniques. You can now map TTPs"; admin-only buttons shown to analysts and a 403 blanks the matrix.
- F-7 `errorMessages.ts:9-24`: every 4xx becomes "Request failed (N)", discarding the backend's sanitised `detail` ("A collection run is already in flight", "File too large").
- F-8 `AssistantContext.tsx:248-253`, `query.py:60-67`: with `model: "none"` the raw retrieval dump is rendered as the assistant's answer; grounding code nulls the one signal.
- F-9 `api.ts:26-38`, `login/page.tsx:29-32`: 401 interceptor clears only `auth_token`/`auth_user`; `activeProject` and `assistant_thread:*` (RAG answers, verbatim excerpts) survive to the next analyst on the same browser.
- F-10 `api.ts:763-770`, `products/page.tsx:257-264`: client type omits `requirement`/`pir_id`, so UI-generated products are never grounded in a PIR (the backend docstring records the resulting failure mode).

**Frontend pages (P)**
- P-10 `network/page.tsx:2434-2454`, `graph.py:80-89`: `/graph` edges omit `evidence`/`method`; panel always says "No captured evidence — re-run extraction" and shows `[object Object]` as source document.
- P-11 `network/page.tsx:487-508`: clearing a snapshot view relies on `setIslandThreshold(0)` re-running the effect; no-op at the default 0, graph stays filtered.
- P-12 `network/page.tsx:707-725`: relationships never cleared on select or failure; B's header over A's list.
- P-13 `collections/page.tsx:1091-1093`: plan delete with no confirm and no catch (collection-plans page has both).
- P-14 `collections/page.tsx:383-392`: rejected sources matched by display name; delete failure swallowed; execute proceeds.
- P-15 `collections/page.tsx:206-227`: every ACTIVE plan (i.e. every executed plan) polled every 3 s forever, unawaited ticks overlap; ~820 req/min with 20 plans.
- P-16 `search/page.tsx:205-295`, `search.py:13-22`: copy says "matches names and text"; backend matches names only, capped 50 alphabetically, `total` = capped length.
- P-17 `project/[id]/page.tsx:43-88`: "Active Collections" is `reports.length`; "Unresolved Gaps" is connected-component count (a connected graph shows 1); every fetch `.catch(() => null)` renders "Project not found" on any error.
- P-18 `geo/page.tsx:258-260,480-482`, `geo.py:107-120`: `connection_count` is all relationships of all locations, place-to-place counted twice; map draws `edges`; API already returns `edge_count`.
- P-19 `admin/page.tsx:110-336`: every loader swallows errors into plausible values; a failed proxy load shows "Direct" and Save then persists `direct` over Tor/VPN.
- P-20 / A-Low `personas.py:5,101-123`, `llm-hub/page.tsx:137-167`: persona mutations require auth only, not admin; POST with a built-in id overwrites it; activation is global and shapes every user's PIR decomposition; in-memory (contradicts root CLAUDE.md). UI failures reach only `console.error`.
- P-21 `collection-plans/page.tsx:77-121,349-353`: plans and dashboard share one `Promise.all` (dashboard 500 → "No collection plans yet"); detail panel keeps the previous plan on failure, and Transition/Delete act on its id.

**Infra / CI / tests (I)**
- I-9 `.github/workflows/ci.yml:65-138`, `Dockerfile:13`: root Dockerfile never built in CI; CI on 3.11, image on 3.12, no `.python-version`; `main` has no branch protection (3 of the last 8 pushes failed E2E after landing).
- I-10 `ci.yml:95-156`, `Dockerfile:2,18`: Node 20 (EOL 2026-04-30) in CI and build stages; runtime Node is Debian's unpinned apt package, different from the build Node.
- I-11 `tests/test_cohere_collection_pipeline.py:57-98`, `test_attack_mapping.py:104,126`: 10 tests exercise a copy of the extraction parser that has already drifted from `extraction.py:1233`; mapping/clustering/extraction parsers hand-roll fence stripping and are tested only on bare JSON.
- I-12 `tests/test_auth_api_key.py`: nothing tests `REQUIRE_SECURE_AUTH=true` refusing to boot, the admin/admin seed refusal, `/api/auth/login`, or the lockout.

### Low

- A: rate-limiter cleanup rebinds `ip` (`middleware.py:69-84`); `/api/query` returns context as `answer` on LLM failure (`query.py:60-67`); batch delete counts nonexistent ids, invalid proxy mode coerced to `direct` with 200, unbounded `limit`/`offset` (negative → 500), untyped `/graph/influence` body; `@cached` cap is not a cap and eviction races threadpool inserts (`cache.py:45-51`); MCP mountable under secure auth, no CSP, API key compared with `==`, login skips bcrypt for unknown users (timing enumeration).
- R: `/execution-status` bypasses `has_live_run`; topic summary streams `str(e)`; summary cache ignores `level`/history; topic edit endpoints write rows nothing reads (`topics.py:82-161`); ACH/Admiralty parsers reject bold/table forms and clamp 1.5 → 1.0 (`analytic_agents.py:47-58,371-391,478-490`); `DELETE /reports/{id}` deletes any node by id with no type/project check (`reports.py:320-324`); `update_plan` accepts any status string (revives ARCHIVED) and overlong fields → 500; executing a plan with no automated sources sets ACTIVE and never runs the requirement loop; `assess_pir` reopens ARCHIVED PIRs; activity trail loaded whole every 3 s.
- C: 100.64.0.0/10 (CGNAT, Alibaba metadata, Tailscale) not blocked (`url_guard.py:36`); proxy mode fails open to direct with no signal (`proxy.py:50-91`); "not satisfied" logged as "satisfied" (`agentic.py:1027-1031`); formula-injection quoting applied at ingest corrupts negative coordinates (`flat_file.py:58-80`); CLAUDE.md says `_validate_urls` calls the guard, it does not (`agentic.py:375-406`); upload parse errors return raw exception text.
- G: LLM type canon maps Satellite/Vehicle/Hardware/Tank to non-types → `:Custom` (`extraction.py:418-420`); check-then-create races on entity/edge creation (*Likely*); `collection_sources.collection_status` missing from `_ADDITIVE_COLUMNS` (`db/engine.py:42-46`; the only post-ship column not covered); topic nodes counted as `llm`-refined with no name; duplicate YAML keys map "deploy"/"station" to DEPLOYED_AT (`data/relationship_types.yaml:86,98,128-129`); `_get_agentic_provider` re-implements provider precedence and overrides an operator's Ollama choice with any cloud key (`agentic.py:273-318`), topics provider ignores DB keys; GraphRAG never receives the foundation prompt (`graph_rag.py:306`, `skills/loader.py:31-44`); `init_db` cannot degrade when pgvector is missing; k-means seeded with `hash(project_id)` (re-salted per process).
- E: MCP `streamable_http_app` lifespan never runs when mounted (every request 500, *Likely*), endpoint is `/mcp/mcp`, `query_corpus` is sync and returns an unawaited coroutine, `hops` unclamped; `refang` rewrites "(DOT)"/"(AT)" in ordinary prose before spaCy (`observables.py:21-23`); KEV and NVD overwrite each other's `severity`; geoip over plain HTTP through a possible Tor exit; ATT&CK/CWE/CAPEC downloads cached before validation, "latest" never expires; D3FEND caches a schema change as "no countermeasures" for 30 days and accepts any `tid`.
- F: sidebar collections pulse polls legacy `/collections` for all projects every 30 s and counts never-run PENDING rows; `collapseToCommunities` merges all `community_id: -1` nodes into one super-node; ATT&CK drawer shows out-of-order responses; TopicMindMap cross-reference links never appear and "Collapse all" rebuilds per click (lint warning `:470`); GraphVisualization drops selection/ego styling on rebuild (lint warnings `:486-489`); histogram fetch error renders as "No dated events"; GeoMap double-inits under Strict Mode; MobileBottomNav "Close" re-opens; dead `collectionsApi.approve` posts to a missing route; PIR delete has no confirm; chat input re-parses every message's markdown per keystroke.
- P: "Refined PIR" extracted with `[""]` (single-char class) greedy regex over model prose (`collections/page.tsx:291-298`); saving a viewed history item uses the current form's type/entities; data-sources summary/context writes into whichever topic is selected when it finishes; geo fast re-selection shows the prior location, sparkline overflows above 9; analysis "none selected = all" grades 10; `entity.properties` never rendered on flattened entities (`entityFields` exists); Evaluate Source uses the active project, not the document's.
- I: Redis and Celery declared, deployed and documented but never imported; default e2e run overwrites the committed README screenshots (`capture-docs.spec.ts` has no skip guard); compose credentials hardcoded rather than `${VAR:-changeme}`, `uv:latest`/`ollama:latest`/`gluetun:latest`/untagged tor image; root image runs as root, no HEALTHCHECK, Next backgrounded with `&` and unsupervised, `start.sh` never invoked though CLAUDE.md says it is, Next rewrites baked at build time so compose's runtime `BACKEND_URL` does nothing; tautological tests (`test_valid_transitions` asserts `X in ("X", X)`, `test_sql_injection_in_project_id` asserts pass-through), 13 files use deprecated `get_event_loop().run_until_complete`.

## Cross-cutting themes

**1. The four silent-failure classes are now the dominant defect shape.**
Roughly two thirds of Medium and High findings are one of: a 200 with an
empty or zero body and no reason (embed 0, mapped 0, api_feed 0, pretty-JSON
0, runner SUCCESS with 0 docs); a failure rendered as a plausible value
(cached empty enrichment marked "ok", "Systems Nominal" while degraded,
probability 1.0 from "15%", centrality 0.000, watchlist always empty, report
failure saved as a product, admin "Direct" after a failed load); a settable
flag standing in for evidence (PAUSED ignored by the loop, `REQUIRE_SECURE_AUTH`
checking the setting rather than the stored hash, legacy runner status); and
model output parsed by the requested shape (verdict lines, refinement split,
ACH tables, ATT&CK matches, hybrid extraction JSON, `bool("false")`). The
`llm_output.py` helpers exist but are bypassed in at least six parsers.

**2. Cross-layer contract drift with no shared types.** Field-name mismatches
between API and client (`watched_entities`, `degree`, `edge_count`,
`note_type`, `requirement`/`pir_id`, `X-Total-Count`) are hidden by `|| 0`,
`?? []` and `catch {}`. Generating the client types from the backend response
models, or a contract test per `api.ts` function, would have caught all of
them.

**3. Direction and provenance are lost in the graph layer.** Undirected
`get_relationships`, no Document edges, `source_doc_id` set only on create,
agentic Documents without `url`, corroboration counting denials. Several
analyst-facing views (evidence chain, document entities, merge, snapshots,
cyber edges) are wrong for the same root cause.

**4. The API process is doing blocking work.** Sync Neo4j, spaCy, PDF/xlsx
parsing, DNS, and search back-off all run on the single uvicorn worker's
event loop, which also hosts every agentic run and the Railway health check.
`plan_executor.py` shows the correct pattern; nothing else follows it.

**5. Tests assert the code's assumptions.** 1,428 green tests, none of which
fail on any finding above. Parsers are tested on ideal JSON or on a copy of
the parser; the auth fail-closed path, login, lockout, merge, and snapshot
edges have no tests at all.

**6. What ships is not what CI tests.** Root Dockerfile (no Chromium, Python
3.12, Node 20/unpinned apt Node, root user, unsupervised Next) is never built
in CI, which builds `backend/Dockerfile` on Python 3.11 instead.

## Recommended fix order

1. Root `Dockerfile`: install Chromium; build it in CI. (I-1, I-9)
2. `crawler.py`: reject results whose `redirected_url` fails `is_safe_url`; add a per-request hook; block `not is_global`; resolve-and-pin in the guard. (C-1, C-5, C-Low)
3. `auth.py`/`app.py`: treat empty/short `JWT_SECRET` and `API_KEY` as insecure; verify the stored admin hash at boot; add change-password; rightmost `X-Forwarded-For`; per-username throttle. Add the missing auth tests. (A-1..3, I-3, I-12)
4. `store.py`: return `startNode/endNode` from `get_relationships`; fix merge to preserve direction, type and properties; project-scope `get_subgraph`; key `graph_cache` by `(project_id, limit)`. (A-4..7, A-11)
5. `documents.py`: read entities by `source_doc_id`. (A-6)
6. `extraction.py`/`graph_builder.py`: exact-match IOC types in hybrid merge; validate LLM attributes per field; clean relationship endpoint names; type-compatible substring fallback. (G-1, G-2, G-6, G-7)
7. `ollama.py`: raise on non-2xx/`error`; set `num_ctx`. Then delete the dead "no provider" branches or make them reachable. (G-3)
8. `requirement_loop.py`: honour `assessed`; `await` the proxy config and make the test stubs async; wrap `run_agentic_loop` in a handler that writes `plan_failed`; per-plan execute lock. (C-2, C-4, R-3, R-4)
9. `enrichment/service.py`: providers raise on failure; skip apply and cache on error; one shared `RateLimiter`. (E-1, E-2)
10. `topics.py` + `data-sources/page.tsx`: JSON-encode SSE chunks and buffer on the client. (R-1)
11. `llm_output.py`: fix the probability regex boundary; route the verdict, refinement, ACH, mapping, extraction and clustering parsers through it; add prose-prefixed and table-shaped fixtures. (R-5..8, E-6, G-5, I-11)
12. Frontend contracts: `watched_entities`, `degree`, `edge_count`, `model === 'none'` handling, `X-Total-Count` on cyber/timeline/search, `Markdown` `img` block + CSP, `clearSession()`. (F-1, F-9, P-1..3, P-8, P-9)
13. `.env.example:102`; Settings `extra="ignore"` and absorb `JWT_SECRET`/`ENCRYPTION_KEY`/`CORS_ORIGINS`; `uv lock --upgrade`; `npm update axios`; Next 15.5 plan; enable GitHub security features and Dependabot. (I-2, I-4..8)
14. `asyncio.to_thread` around every sync store/spaCy/parse call; shared `:Entity` label with an indexed `id`. (G-4)

## Not verified

- Railway environment values (`REQUIRE_SECURE_AUTH`, `JWT_SECRET`, `TRUST_PROXY_HEADERS`, `MCP_ENABLED`) and whether the edge appends or overwrites `X-Forwarded-For`. A May 2026 local deploy note records admin/admin on the live instance; check that first.
- The production image was not built; the Chromium failure is inferred from the Dockerfile and crawl4ai source.
- No live exploitation of the redirect or DNS-rebinding paths; no external requests were made.
- Neo4j and Postgres were down locally, so timings, pgvector column width, and whether existing projects have any Document edges were not measured.
- `pytest` was not run by the reviewers; the pass count comes from the latest `main` CI run.
- How often production models emit tables, bold labels or percentages; the parser findings assume they do at a meaningful rate (the repo's own findings docs say they do).
- The d3 "node not found" crash (P-6), the Cohere 96-text embed cap (G-10), the MCP lifespan failure (E-Low), and the embedding-width poisoning (G-9) are reasoned from library source or documentation, not reproduced.
