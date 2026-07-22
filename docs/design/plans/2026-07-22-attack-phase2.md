# ATT&CK Phase 2 — Plan (text→technique mapping + attribution)

Extends `docs/design/specs/2026-07-22-mitre-attack-integration-design.md`. Phase 1
resolves TTPs that carry an explicit T-code. Phase 2 maps **prose** to techniques
and adds **threat-actor attribution** by technique overlap.

## Decisions

- **Mapping = RAG, not a classifier.** Embed each ingested `AttackTechnique`
  (`"<name>. <description>"`) into pgvector (reusing the `EmbeddingProvider`
  orchestrator + the `chunk_embeddings`/`vector_search` pattern) in a new
  `attack_technique_embeddings` table. To map an entity: embed its text, cosine-
  retrieve top-k candidate techniques, then an LLM skill confirms which actually
  apply (IDs + confidence + rationale). Grounding the LLM in retrieved candidates
  sidesteps the 697-way classification problem.
- **Embedding is an explicit admin step** (`POST /attack/embed`), not folded into
  ingest — embedding 697 techniques costs provider calls/time; keep it opt-in and
  idempotent (upsert). Dimension mirrors the existing `chunk_embeddings` handling.
- **Map TTP entities first** (most direct value for the matrix); document-level
  mapping is a follow-on. `POST /attack/map?project_id=` maps the project's TTP
  entities NOT already resolved by T-code, via RAG+LLM, creating
  `(:TTP)-[:MAPS_TO {confidence, method:"llm"}]->(:AttackTechnique)`. Phase-1 T-code
  resolution sets `method:"tcode", confidence:1.0`.
- **LLM provider:** route through the orchestrator's extraction/collection provider
  (config) so bulk mapping won't drain a rate-limited cloud key; degrade cleanly if
  no embedding/LLM provider is reachable (skip + report, never 500).
- **Attribution is suggestive, not definitive** (credibility guardrail — no
  overclaiming). Rank ATT&CK Groups by shared-technique overlap with the project's
  observed techniques; show count + coverage %, top 10, with the shared technique
  list. Metric: `shared = |observed ∩ group_techniques|`, `coverage = shared/|observed|`.
- **Fast-follows folded in:** `resolve_ttps` N+1 → single `UNWIND` batch; an
  `asyncio.Lock` around ingest so concurrent admin triggers don't double-fetch.

## API additions
- `POST /attack/embed` (admin) → `{embedded: int}` — embed all techniques into pgvector.
- `POST /attack/map?project_id=` → `{mapped: int, skipped: int}` — RAG+LLM map unresolved TTPs.
- `GET  /attack/attribution?project_id=` → `{observed_total: int, groups: [{id, name, shared_count, coverage: float, shared_techniques: [{id, name}]}]}`.
- Matrix technique cells + technique-detail `related_entities` carry the map `method`/`confidence`.

## Frontend
- ATT&CK Matrix: a **"Map TTPs → ATT&CK (AI)"** action (POST /map then reload); mapped
  cells distinguish `tcode` vs `llm` (e.g. a small "AI" badge + confidence). An embed
  affordance if techniques aren't embedded yet.
- An **Attribution** panel (Threat Actors tab): ranked candidate groups with coverage %
  and shared techniques, framed as *suggestive overlap, not confirmed attribution*.

## Out of scope (Phase 3+)
Document-level mapping, CVE→ATT&CK chaining, D3FEND, ATT&CK-structured products.
