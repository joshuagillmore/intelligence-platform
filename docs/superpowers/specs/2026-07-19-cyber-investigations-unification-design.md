# Cyber Investigations Unification + Enrichment Sources — Design

- **Date:** 2026-07-19
- **Status:** Proposed
- **Scope:** Unify the platform's cyber-investigation capabilities and introduce
  external cyber data sources (WHOIS/RDAP, DNS, GeoIP, cert transparency,
  CISA KEV, NVD), free/keyless tier first, keyed providers designed-in for later.
- **Decisions locked with owner:** free/keyless sources first; on-demand
  "Investigate" + selective cheap auto-enrichment; keyed providers
  (Shodan/VirusTotal/AbuseIPDB/OTX) architecture-ready but deferred.

## Problem

Documents are the platform's only real input for cyber material. IPs, domains,
hashes, CVEs, and MITRE technique IDs are pulled from document text by regex
(`services/extraction.py:38-63`) and stored as first-class Neo4j nodes — but
that is where the investigation stops:

1. **Nothing enriches an observable.** `Domain.dns_records`, `Domain.registrant`,
   `IPAddress.asn`, `IPAddress.geolocation` exist in the models
   (`models/entities.py:112-124`) and are never populated by anything except a
   lucky LLM guess. There is no WHOIS, DNS, GeoIP, reputation, or vulnerability
   lookup anywhere in the codebase — `services/enrichment.py` is actually
   NetworkX graph analytics (a misnomer), and geocoding is a hardcoded
   ~180-place dict.
2. **The analyst has no "investigate" action.** The `/network` entity panel
   offers LLM assessment/gap-analysis, watchlist, and type-change — no lookup.
   The `/cyber` page has stat cards for severity/enriched/attributed that are
   hollow because no pipeline populates those properties, and its MITRE matrix
   is 8 hardcoded tactics with substring matching.
3. **Cyber UX is fragmented.** `/cyber` re-implements a thinner copy of the
   `/network` detail panel; entity styling (TYPE_COLORS) is duplicated in four
   files and already drifting; investigating an IOC means page-hopping.
4. **Extraction misses common threat-intel forms.** No defanging support
   (`1.2.3[.]4`, `hxxp://`, `evil[.]com` are silently missed), no URL or email
   observables, RESOLVES_TO edges exist only when the LLM emits them, and the
   BTC address pattern is dead code.
5. **Structured cyber sources have no connector.** The `database` connector
   scrapes HTML pages; `api_feed` is a thin GET-only JSON fetcher. There is no
   registry/feed client for NVD, KEV, or certificate transparency.

## Design Goals

- **One enrichment subsystem** — a provider registry (mirroring
  `connectors/base.py`) that any cyber source plugs into, with caching,
  rate-limiting, provenance, and VPN/Tor egress via `ProxiedClient` for free.
- **On-demand + selective auto** — an analyst-triggered **Investigate** action
  on any cyber entity, plus cheap keyless lookups (DNS, GeoIP, KEV flag) that
  run automatically when a cyber entity first lands in the graph. Everything
  cached in Postgres and refreshable.
- **Evidence discipline** — enrichment writes carry `method="enrichment:<provider>"`,
  a source URL, and a response snippet as evidence, same as extracted relations.
- **Deterministic beats generative** — DNS lookups create RESOLVES_TO edges;
  KEV/CVSS populate severity. Real data replaces the hollow `/cyber` stats.
- **Unify, don't duplicate** — shared entity styling + a shared enrichment
  panel used by both `/network` and `/cyber`.
- **Keyed-ready** — Shodan/VT/AbuseIPDB/OTX slot into the same ABC later,
  with keys held in the existing encrypted `ApiKey` store and admin CRUD.

## Non-Goals (this iteration)

- MISP / OpenCTI / STIX-TAXII **import** (export already exists); revisit when
  a TIP is in play.
- Keyed reputation providers (Shodan, VirusTotal, AbuseIPDB, OTX) — designed
  for, not built.
- Scheduled re-enrichment — `schedule_cron` columns exist but the platform has
  no scheduler runtime yet; periodic refresh lands with that runtime, not here.
- ASN/CIDR/port/mutex/JA3 as first-class entity types (ASN stays a property).
- Full MITRE ATT&CK catalog integration (matrix stays, gains real technique
  data only insofar as TTP entities are enriched from extraction).

## Architecture

### Backend — new package `intel_platform/enrichment/`

```
enrichment/
├── __init__.py        # imports providers → registry side-effect (like connectors/)
├── base.py            # EnrichmentProvider ABC + @register_provider + PROVIDER_REGISTRY
├── service.py         # enrich_entity() orchestrator + auto_enrich hook
├── cache.py           # EnrichmentRecord Postgres cache (TTL per provider) + rate limiter
├── observables.py     # normalization: defang/refang, type→provider eligibility
└── providers/
    ├── rdap.py        # WHOIS via RDAP  (domains + IPs)     — keyless
    ├── dns.py         # DNS records + reverse PTR via DoH   — keyless
    ├── geoip.py       # IP geolocation/ASN (ip-api.com)     — keyless
    ├── certs.py       # crt.sh certificate transparency     — keyless
    ├── kev.py         # CISA Known Exploited Vulnerabilities— keyless
    └── nvd.py         # NVD CVE API 2.0 (CVSS, products)    — keyless, key optional
```

**`EnrichmentProvider` ABC** (mirrors `SourceConnector`):

```python
class EnrichmentProvider(ABC):
    name: str                      # "rdap", "dns", ...
    supported_types: set[str]      # {"IPAddress", "Domain", ...}
    requires_key: bool = False
    cache_ttl: timedelta           # per-provider freshness window
    auto: bool = False             # runs in the selective auto-enrich pass

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult: ...
```

`EnrichmentResult` = `properties: dict` (merged onto the node),
`related: list[RelatedEntity]` (new nodes + typed edges, e.g. DNS A record →
`(:Domain)-[:RESOLVES_TO]->(:IPAddress)`), `raw: dict` (audit payload),
`source_url: str` (evidence).

**Provider table (free tier):**

| Provider | Types | Populates | Edges created | TTL | auto |
|---|---|---|---|---|---|
| `rdap` | Domain, IPAddress | registrant, registrar, registration/expiry dates; IP netblock + ASN org | — | 7 d | no |
| `dns` | Domain | dns_records (A/AAAA/MX/NS/TXT/CNAME), PTR | Domain→RESOLVES_TO→IPAddress | 1 d | yes |
| `geoip` | IPAddress | asn, geolocation (lat/lng, city, country, org) | — | 30 d | yes |
| `certs` | Domain | cert issuers, SAN count | Domain→ASSOCIATED_WITH→Domain (SAN-discovered) | 7 d | no |
| `kev` | Vulnerability | known_exploited=true, kev_date_added, severity="critical" | — | 1 d | yes |
| `nvd` | Vulnerability | cvss_score, severity, description, affected_products | — | 7 d | no |

DNS uses DNS-over-HTTPS (Cloudflare `cloudflare-dns.com/dns-query`, JSON) so it
is plain HTTPS GET → works through `ProxiedClient` (VPN/Tor egress, fail-safe
direct) with no raw-socket dependency. GeoIP uses ip-api.com's keyless JSON
endpoint (45 req/min — the rate limiter matters); RDAP uses the IANA bootstrap
registries (`rdap.org` follows referrals); certs uses `crt.sh?output=json`; KEV
is one CISA JSON catalog (cached daily, membership test); NVD is the CVE API 2.0
(5 req/30 s keyless, 50 with an optional key). Every one is an HTTPS GET, so the
whole free tier inherits `ProxiedClient` egress with **zero** new network code.

**`EnrichmentService.enrich_entity()`** (`service.py`) is the orchestrator:
1. Normalize the observable (`observables.refang()` — turn `1.2.3[.]4`/`hxxp` back
   into real values before lookup) and validate the type.
2. For each registered provider whose `supported_types` matches (and whose key,
   if `requires_key`, is present), check `cache.get(provider, value)`; on miss,
   acquire a rate-limit slot and call `provider.lookup()`.
3. Merge `EnrichmentResult.properties` onto the Neo4j node (`store.update_entity`),
   upsert `related` nodes/edges through `graph_builder` with
   `method="enrichment:<provider>"`, `evidence=<source_url>`, and persist `raw`
   to the cache. Failures are per-provider isolated and logged — one dead
   provider never fails the investigation (same fail-soft posture as extraction).
4. Return a consolidated `EntityEnrichment` (per-provider status + merged view).

**Auto-enrich hook.** `service.auto_enrich(entity)` runs only the providers with
`auto=True` (dns, geoip, kev). It is called once, fire-and-forget, when a cyber
entity is **first created** — from `graph_builder.build_graph_from_extractions`
after node upsert (guarded by a "not already enriched" check on the node so
re-ingestion doesn't re-hit providers). It respects the same cache + limiter, so
a re-seen IOC across documents costs nothing.

### Backend — data model

- **New table `EnrichmentRecord`** (`db/models.py`, created at boot by `init_db`,
  matching the no-Alembic convention): columns `id`, `provider`, `observable`
  (normalized), `entity_type`, `payload` (JSON), `source_url`, `fetched_at`,
  `expires_at`; unique `(provider, observable)`. This is the cache **and** the
  audit trail of every external call. `cache.py` reads/writes it and enforces
  `cache_ttl`; a background-free "stale but present" row is still returned while
  a refresh is requested (never block the analyst on a slow provider).
- **Entity model:** no new entity *types* this iteration (per Non-Goals). Reuse
  existing typed props — `IPAddress.asn`/`geolocation`, `Domain.dns_records`/
  `registrant`/`registration_date`, `Vulnerability.cvss_score`/`affected_products`.
  Add three generic node props written by enrichment: `enriched` (bool),
  `enriched_at` (iso), `known_exploited` (bool, KEV). These are exactly the
  fields the `/cyber` stat cards already read but nothing populates today.
- **Relationships:** DNS resolution creates the deterministic
  `(:Domain)-[:RESOLVES_TO]->(:IPAddress)` edge that today only appears when the
  LLM guesses it. `RESOLVES_TO` is already in `VALID_REL_TYPES` — no schema change.

### Backend — API surface (`api/routes/enrichment.py`, new router)

- `POST /enrichment/entities/{entity_id}` — the **Investigate** action. Runs all
  eligible providers for the entity's type (respecting cache), returns the
  merged `EntityEnrichment`. Admin/analyst-gated like other mutating routes.
- `GET /enrichment/entities/{entity_id}` — return the cached enrichment view
  without hitting providers (what the panel loads on open).
- `GET /enrichment/providers` — list registered providers, their supported types,
  `requires_key`, and whether a key is present (drives the admin card + panel
  affordances). Mirrors the `/admin/api-keys` + `_provider_has_active_key` idiom.
- `POST /enrichment/entities/{entity_id}/refresh` — force-bypass cache for one
  provider (`?provider=`), for the panel's per-source refresh button.

`ProxiedClient` gains a **`post()`** and richer `get(params=, headers=)** (it is
GET-only today) so providers can pass query params/headers cleanly; the free tier
is GET-only, but this unblocks keyed providers without a second HTTP wrapper.
A small token-bucket **rate limiter** (per provider name) lives in `cache.py`,
backed by the existing Redis if configured, else an in-process fallback (matches
the `graph_cache` in-memory precedent) — sufficient for a single-worker deploy.

### Backend — extraction hardening (small, high-leverage)

- **Defang/refang** (`observables.py`, reused by both extraction and enrichment):
  before regex, run a refang pass (`[.]`→`.`, `hxxp`→`http`, `(dot)`→`.`,
  `[@]`→`@`) so defanged IOCs from threat-intel text are caught. This is the
  single highest-yield extraction fix and is provider-independent.
- **URL and Email observables** — add `URL` and `EmailAddress` regex to
  `_extract_cyber_entities` and matching enum/model/label entries. Scoped-in here
  because refang + URLs are what make pasted threat reports actually parse; kept
  minimal (no ASN/port/mutex — those remain Non-Goals).
- Remove the dead `BTC_PATTERN` or wire it to a `CryptoAddress` prop — decision
  deferred to the plan; not blocking.

### Frontend — unify then surface

- **`lib/entityStyles.ts` (new)** — single source of truth for `TYPE_COLORS` +
  (new) per-type icon, replacing the four drifting copies
  (`GraphVisualization.tsx`, `network`, `watchlist`, `cyber`). Pure refactor,
  no behavior change, done first so everything downstream shares it.
- **`components/EnrichmentPanel.tsx` (new)** — one shared panel that renders the
  enrichment view (WHOIS/DNS/GeoIP/certs/KEV/CVSS sections, per-source status +
  refresh, "Investigate" button calling `enrichmentApi.investigate`). Embedded in
  **both** the `/network` detail panel and the `/cyber` expand-row, ending the
  two-parallel-UIs problem.
- **`/cyber` real data** — severity/enriched/attributed cards read the now-populated
  props; `known_exploited` drives a "Known Exploited (KEV)" badge; the IOC table
  gains an Investigate affordance. MITRE matrix stays as-is (Non-Goal), but TTP
  rows show enriched descriptions when present.
- **`enrichmentApi`** added to `lib/api.ts` (investigate / get / providers /
  refresh). No other client rewiring.
- **Graph nodes** gain per-type icons from `entityStyles` (addresses the
  "circles only" gap) — small, optional polish within the same refactor.

### Egress, security, config

- Every provider call goes through `ProxiedClient`, so cyber lookups honor the
  admin VPN/Tor egress mode and fail-safe to direct — an analyst can WHOIS/DNS a
  hostile domain from the Surfshark exit, not their real IP. This reuses the
  proxy work already merged.
- SSRF: enrichment targets are provider-fixed API hosts (not user URLs), so the
  `scraper.py` guard isn't in this path, but provider base URLs are allow-listed
  constants and the observable is passed as a query param, never as the host.
- Keys (deferred providers) reuse the encrypted `ApiKey` table + `/admin/api-keys`
  CRUD; NVD's optional key is the first, lowest-stakes consumer. New settings
  (base URLs, TTLs, `enrichment_auto_enabled`) follow the flat `Settings` pattern
  and are mirrored in `.env.example`. Runtime auto-enrich on/off is an `AppSetting`
  (like `collection_proxy_mode`), toggled from the admin card.

## Testing

- `tests/test_enrichment_providers.py` — each provider's `lookup()` against a
  recorded fixture payload (AsyncMock the HTTP call), asserting property mapping +
  edge creation; refang unit tests in `tests/test_observables.py`.
- `tests/test_enrichment_service.py` — cache hit/miss, rate-limit gating,
  per-provider failure isolation, auto-enrich runs only `auto=True` providers.
- `tests/test_enrichment_route.py` — Investigate/get/providers/refresh, auth gating.
- `conftest` already forces `EXTRACTION_MODE=nlp`; enrichment tests never hit the
  network (all mocked). Definition of done: `uv run pytest` + `uv run ruff check .`.

## Rollout (phases map 1:1 to the implementation plan)

1. **Observables + extraction hardening** (refang, URL/email) — value even before
   any provider; unblocks defanged-IOC parsing.
2. **Enrichment core** — base ABC, registry, cache table, service, rate limiter,
   `ProxiedClient.post()`. No providers yet; tested with a fake provider.
3. **Free providers** — rdap, dns, geoip, kev, nvd, certs, each behind its own
   task + fixture test. DNS RESOLVES_TO + GeoIP asn/geo are the first visible wins.
4. **API + auto-enrich hook** — router, wire `auto_enrich` into `graph_builder`.
5. **Frontend unify** — `entityStyles`, `EnrichmentPanel`, `/cyber` real stats,
   `enrichmentApi`.
6. **Admin card + docs** — providers list, auto-enrich toggle, `.env.example`.

Keyed providers (Shodan/VT/AbuseIPDB/OTX) are a later, additive phase: each is
one new file in `providers/` with `requires_key=True` — no core changes.

## Open questions

- **GeoIP provider choice** — ip-api.com (keyless, 45/min, non-commercial terms)
  vs bundling MaxMind GeoLite2 (offline, redistribution terms, ~70 MB DB). Start
  with ip-api.com behind the abstraction; swapping is one file.
- **Auto-enrich default** — ship **off**, opt-in via the admin toggle, to avoid
  surprise egress on first ingest; revisit after the owner sees volume.
- **Reverse-DNS/PTR fan-out** — cap related-node creation per lookup (e.g. first
  10 DNS records) so a wildcard domain can't explode the graph; enforced in
  `service.py`.