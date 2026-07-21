# Cyber Investigations Unification + Enrichment Sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the platform from *extract-and-stop* into *extract-and-investigate*. Add a unified enrichment subsystem that pulls related cyber data (WHOIS/RDAP, DNS, GeoIP, cert transparency, CISA KEV, NVD) for observables the platform already models, exposes an analyst **Investigate** action, and unifies the fragmented cyber UI — free/keyless sources first, keyed providers architecture-ready but deferred.

**Architecture:** New backend package `intel_platform/enrichment/` mirrors the existing `connectors/` plugin pattern: an `EnrichmentProvider` ABC + registry, a Postgres-backed cache/rate-limiter, an orchestrator service, and one file per provider. Every provider call is an HTTPS GET through the existing `ProxiedClient`, so cyber lookups inherit VPN/Tor egress for free. Frontend consolidates four drifting `TYPE_COLORS` copies into one module and adds a shared `EnrichmentPanel` used by both `/network` and `/cyber`.

**Tech Stack:** Python 3.11 (uv), FastAPI, async SQLAlchemy + Postgres, Neo4j, httpx via `ProxiedClient`, Next.js 14, TypeScript.

**Spec:** `docs/superpowers/specs/2026-07-19-cyber-investigations-unification-design.md`

**Owner decisions (locked):** free/keyless first; on-demand Investigate + selective cheap auto-enrich (default OFF); keyed providers deferred; no new entity *types* beyond URL/Email; no scheduler, no STIX/TAXII import this iteration.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/src/intel_platform/enrichment/__init__.py` | Create | Import providers for registry side-effect (like `connectors/__init__.py`) |
| `backend/src/intel_platform/enrichment/observables.py` | Create | `refang()`/`defang()`, observable validation, type→provider eligibility |
| `backend/src/intel_platform/enrichment/base.py` | Create | `EnrichmentProvider` ABC, `EnrichmentResult`/`RelatedEntity`, `@register_provider`, `PROVIDER_REGISTRY`, `get_providers_for(type)` |
| `backend/src/intel_platform/enrichment/cache.py` | Create | `EnrichmentRecord` read/write + TTL, token-bucket rate limiter (Redis if present, else in-proc) |
| `backend/src/intel_platform/enrichment/service.py` | Create | `enrich_entity()` orchestrator + `auto_enrich()` hook |
| `backend/src/intel_platform/enrichment/providers/rdap.py` | Create | WHOIS via RDAP (Domain, IPAddress) — keyless |
| `backend/src/intel_platform/enrichment/providers/dns.py` | Create | DNS records + PTR via DoH; creates `RESOLVES_TO` — keyless, `auto` |
| `backend/src/intel_platform/enrichment/providers/geoip.py` | Create | IP geolocation + ASN (ip-api.com) — keyless, `auto` |
| `backend/src/intel_platform/enrichment/providers/kev.py` | Create | CISA KEV membership → `known_exploited` — keyless, `auto` |
| `backend/src/intel_platform/enrichment/providers/nvd.py` | Create | NVD CVE API 2.0 (CVSS, products) — keyless, key optional |
| `backend/src/intel_platform/enrichment/providers/certs.py` | Create | crt.sh certificate transparency — keyless |
| `backend/src/intel_platform/collection/proxy.py` | Modify | Add `post()` + `get(params=, headers=)` to `ProxiedClient` |
| `backend/src/intel_platform/db/models.py` | Modify | Add `EnrichmentRecord` table |
| `backend/src/intel_platform/models/entities.py` | Modify | Add `URL`, `EmailAddress` enum + models; `enriched`/`enriched_at`/`known_exploited` props |
| `backend/src/intel_platform/models/type_hierarchy.py` + `data/type_hierarchy.yaml` | Modify | Register `URL`, `EmailAddress` under Cyber |
| `backend/src/intel_platform/services/extraction.py` | Modify | Refang pass before regex; URL/Email patterns |
| `backend/src/intel_platform/services/graph_builder.py` | Modify | Fire-and-forget `auto_enrich` after cyber-node upsert (guarded) |
| `backend/src/intel_platform/graph/store.py` | Modify | `update_entity(id, props)` if not already present |
| `backend/src/intel_platform/api/routes/enrichment.py` | Create | Investigate / get / providers / refresh router |
| `backend/src/intel_platform/api/app.py` | Modify | Register enrichment router |
| `backend/src/intel_platform/api/routes/admin_config.py` | Modify | `GET /admin/enrichment/providers`, auto-enrich `AppSetting` toggle |
| `backend/src/intel_platform/config.py` + `.env.example` | Modify | Provider base URLs, TTLs, `enrichment_auto_enabled`, optional NVD key |
| `backend/tests/test_observables.py` | Create | refang/defang + validation |
| `backend/tests/test_enrichment_providers.py` | Create | Per-provider `lookup()` against fixtures |
| `backend/tests/test_enrichment_service.py` | Create | Cache, rate-limit, failure isolation, auto-enrich selection |
| `backend/tests/test_enrichment_route.py` | Create | Route behavior + auth gating |
| `frontend/src/lib/entityStyles.ts` | Create | Single `TYPE_COLORS` + icons |
| `frontend/src/components/EnrichmentPanel.tsx` | Create | Shared enrichment/Investigate panel |
| `frontend/src/lib/api.ts` | Modify | `enrichmentApi` client |
| `frontend/src/app/network/page.tsx`, `app/cyber/page.tsx`, `app/watchlist/page.tsx`, `components/GraphVisualization.tsx` | Modify | Use `entityStyles`; embed `EnrichmentPanel`; real `/cyber` stats |
| `frontend/src/app/admin/page.tsx` | Modify | "Cyber Enrichment" card (providers list + auto-enrich toggle) |

---

## Phase 1 — Observables + extraction hardening

*Value before any provider exists: defanged IOCs and URLs finally parse.*

### Task 1.1: Refang/defang + observable helpers
**Files:** Create `enrichment/observables.py`, `tests/test_observables.py`

- [ ] **Step 1 — failing test.** In `test_observables.py`, assert `refang("1.2.3[.]4") == "1.2.3.4"`, `refang("hxxps://evil[.]com/x") == "https://evil.com/x"`, `refang("a(at)b(dot)com") == "a@b.com"`, and that `defang()` round-trips an IP. Assert `classify_observable("8.8.8.8") == "IPAddress"`, `classify_observable("evil.com") == "Domain"`, `classify_observable("http://x.com/a") == "URL"`, `classify_observable("a@b.com") == "EmailAddress"`.
- [ ] **Step 2 — implement** `refang`, `defang`, `classify_observable`, and `eligible_providers(entity_type)` (thin wrapper over the registry, added in 2.2). Pure functions, no I/O.
- [ ] **Step 3** — `uv run pytest tests/test_observables.py` green, `ruff check` clean.

### Task 1.2: Wire refang + URL/Email into extraction
**Files:** Modify `services/extraction.py`, `models/entities.py`, `models/type_hierarchy.py`, `data/type_hierarchy.yaml`

- [ ] **Step 1 — failing test.** Extend `tests/test_extraction.py`: a document containing `hxxp://evil[.]com` and `bad[.]actor[.]ru` yields a `URL`/`Domain` entity; a defanged `1.2.3[.]4` yields an `IPAddress`. (Runs in `nlp` mode per conftest.)
- [ ] **Step 2 — implement.** Add `URL` + `EmailAddress` to `EntityType` enum + Pydantic models (mirror `IPAddress`), register under the Cyber category in both hierarchy sources, add `URL_PATTERN`/`EMAIL_PATTERN` to `_extract_cyber_entities`, and run `observables.refang()` on the text (or per-match window) before the existing regex pass. Keep existing IP/domain/hash/CVE/TTP patterns intact.
- [ ] **Step 3** — pytest + ruff green. Confirm no regression in existing extraction tests.

---

## Phase 2 — Enrichment core (no providers yet)

### Task 2.1: `EnrichmentRecord` cache table + `ProxiedClient.post()`
**Files:** Modify `db/models.py`, `collection/proxy.py`; Create `enrichment/cache.py`; extend `tests/test_collection_proxy.py`

- [ ] **Step 1 — failing test.** In `test_collection_proxy.py`, assert `ProxiedClient` exposes `post()` and that `get(params=...)` forwards query params (mock httpx). In a new `tests/test_enrichment_cache.py`, assert cache miss→set→hit and TTL expiry (`expires_at` in past → miss).
- [ ] **Step 2 — implement.** Add `EnrichmentRecord` (unique `(provider, observable)`) to `db/models.py` (auto-created by `init_db`). Add `post()`/param-aware `get()` to `ProxiedClient` preserving the lazy proxy-resolution + fail-safe-direct behavior. Implement `cache.py`: `get(provider, observable)`, `set(...)`, and a `RateLimiter` token bucket keyed by provider name (Redis-backed if `settings` has a URL, else in-process dict like `graph_cache`).
- [ ] **Step 3** — pytest + ruff green.

### Task 2.2: Provider ABC + registry + result types
**Files:** Create `enrichment/base.py`, `enrichment/__init__.py`; Create `tests/test_enrichment_service.py` (registry portion)

- [ ] **Step 1 — failing test.** Register a `FakeProvider(supported_types={"IPAddress"}, auto=True)` and assert `get_providers_for("IPAddress")` returns it and `get_providers_for("Domain")` does not; assert `requires_key` providers are excluded when no key is present.
- [ ] **Step 2 — implement** `EnrichmentProvider` ABC, `EnrichmentResult`/`RelatedEntity` dataclasses, `@register_provider` + `PROVIDER_REGISTRY` + `get_providers_for()`, mirroring `connectors/base.py`. `__init__.py` imports the providers package for the registration side-effect.
- [ ] **Step 3** — pytest + ruff green.

### Task 2.3: Orchestrator service + auto-enrich (fake provider)
**Files:** Create `enrichment/service.py`; Modify `graph/store.py` (`update_entity`); extend `tests/test_enrichment_service.py`

- [ ] **Step 1 — failing test.** With two fake providers (one `auto`, one not, one raising), assert `enrich_entity()` merges properties, isolates the failing provider (others still applied), honors cache on second call, and that `auto_enrich()` runs only `auto=True` providers. Assert a `RelatedEntity` produces a `RESOLVES_TO`-style edge via a mocked `graph_builder`.
- [ ] **Step 2 — implement** `enrich_entity(entity_id)` and `auto_enrich(entity)` per spec (normalize → eligible providers → cache/limiter → `provider.lookup()` → merge props via `store.update_entity` + upsert related via `graph_builder` with `method="enrichment:<provider>"`/`evidence=source_url` → persist raw). Add `store.update_entity(id, props)` if absent. Cap related-node fan-out (default 10).
- [ ] **Step 3** — pytest + ruff green.

---

## Phase 3 — Free/keyless providers (one task each, fixture-tested)

*Each: add `providers/<name>.py`, a recorded-payload fixture, and a `lookup()` test asserting property mapping + edges. All mock the HTTP call — no network in tests.*

- [ ] **Task 3.1 `dns.py`** (auto) — DoH JSON; map A/AAAA/MX/NS/TXT/CNAME to `dns_records`, PTR for reverse; emit `Domain -RESOLVES_TO-> IPAddress` (capped). *First visible win.*
- [ ] **Task 3.2 `geoip.py`** (auto) — ip-api.com JSON; populate `IPAddress.asn`, `geolocation` (city/country/lat/lng/org). Note ip-api 45/min → limiter.
- [ ] **Task 3.3 `kev.py`** (auto) — CISA KEV catalog (daily cache, membership test); set `known_exploited`, `kev_date_added`, `severity="critical"`.
- [ ] **Task 3.4 `nvd.py`** — NVD CVE API 2.0; populate `cvss_score`, `severity`, `description`, `affected_products`; use optional key if configured (5→50 req window).
- [ ] **Task 3.5 `rdap.py`** — RDAP via IANA bootstrap; registrant/registrar/dates for domains, netblock/ASN-org for IPs.
- [ ] **Task 3.6 `certs.py`** — `crt.sh?output=json`; issuers + SAN count; optional SAN-discovered `ASSOCIATED_WITH` domains (capped).

---

## Phase 4 — API + auto-enrich wiring

### Task 4.1: Enrichment router
**Files:** Create `api/routes/enrichment.py`; Modify `api/app.py`; Create `tests/test_enrichment_route.py`

- [ ] **Step 1 — failing test.** `POST /enrichment/entities/{id}` returns merged view (mock service); `GET` returns cached-only; `GET /enrichment/providers` lists providers with `requires_key`/`has_key`; `refresh?provider=` bypasses cache; all enforce auth like sibling routes.
- [ ] **Step 2 — implement** the four endpoints delegating to `service.py`; register router in `app.py`.
- [ ] **Step 3** — pytest + ruff green.

### Task 4.2: Auto-enrich hook in graph builder
**Files:** Modify `services/graph_builder.py`; extend `tests/test_enrichment_service.py`

- [ ] **Step 1 — failing test.** Building a graph with a new IPAddress triggers `auto_enrich` once; re-building with the same node (already `enriched`) does not.
- [ ] **Step 2 — implement** a guarded fire-and-forget `auto_enrich` call after cyber-node upsert, gated by the `enrichment_auto_enabled` `AppSetting` (default off) and the node's `enriched` flag.
- [ ] **Step 3** — pytest + ruff green.

---

## Phase 5 — Frontend unification

### Task 5.1: Shared entity styling (pure refactor, do first)
**Files:** Create `lib/entityStyles.ts`; Modify `GraphVisualization.tsx`, `network/page.tsx`, `watchlist/page.tsx`, `cyber/page.tsx`

- [ ] Extract the canonical `TYPE_COLORS` (+ per-type icon) into `entityStyles.ts`; replace all four copies with imports. No behavior change. `npm run lint` + `npm run build` green.

### Task 5.2: Shared `EnrichmentPanel` + `enrichmentApi`
**Files:** Create `components/EnrichmentPanel.tsx`; Modify `lib/api.ts`, `network/page.tsx`, `cyber/page.tsx`

- [ ] Add `enrichmentApi` (investigate/get/providers/refresh). Build `EnrichmentPanel` (WHOIS/DNS/GeoIP/certs/KEV/CVSS sections, per-source status + refresh, Investigate button). Embed in the `/network` detail panel and the `/cyber` expand-row (replacing its thin re-implementation). `lint`+`build` green.

### Task 5.3: `/cyber` real stats + node icons
**Files:** Modify `cyber/page.tsx`, `GraphVisualization.tsx`

- [ ] Point severity/enriched/attributed cards at the now-populated props; add a "Known Exploited (KEV)" badge; add Investigate affordance to IOC rows; render per-type node icons from `entityStyles`. `lint`+`build` green.

---

## Phase 6 — Admin card + config + docs

### Task 6.1: Admin "Cyber Enrichment" card
**Files:** Modify `api/routes/admin_config.py`, `frontend/src/app/admin/page.tsx`, `lib/api.ts`

- [ ] Backend `GET /admin/enrichment/providers` + auto-enrich `AppSetting` GET/PUT (mirror `collection_proxy_mode`). Frontend card (following the Collection Egress card pattern): provider list with type/keyless/key-present, and an auto-enrich on/off toggle. Tests + `lint`/`build` green.

### Task 6.2: Config surface + docs
**Files:** Modify `config.py`, `.env.example`; Modify `CODE_REVIEW_REPORT.md`/CLAUDE.md known-issues as needed

- [ ] Add provider base URLs, per-provider TTLs, `enrichment_auto_enabled`, optional `nvd_api_key` to `Settings` + `.env.example` placeholders/comments. Note the new subsystem in `backend/CLAUDE.md` package map.

---

## Definition of done (every task)

- `cd backend && uv run pytest && uv run ruff check .`
- Frontend tasks also: `cd frontend && npm run lint && npm run build`
- No provider test touches the network (all HTTP mocked/fixtured).
- New external calls route through `ProxiedClient` (VPN/Tor egress honored, fail-safe direct).

## Deferred (explicitly out of scope, additive later)

- Keyed providers: Shodan, VirusTotal, AbuseIPDB, OTX — each one new `providers/*.py` with `requires_key=True`, keys in the existing encrypted `ApiKey` store. No core changes.
- Scheduled re-enrichment — lands with a real scheduler runtime (`schedule_cron` columns already exist, unused).
- STIX/TAXII/MISP import; new observable types beyond URL/Email (ASN/port/mutex/JA3).
