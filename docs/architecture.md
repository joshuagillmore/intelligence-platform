# SENTINEL — Architecture

This is the technical companion to the root [`README.md`](../README.md). It goes
one level deeper than the README for a reviewer who wants to understand how the
pieces fit: the two datastores, the LLM orchestration layer, the collection
egress path, and the shape of a request. The three `CLAUDE.md` files (root,
`backend/`, `frontend/`) remain the source of truth for day-to-day conventions;
this doc synthesizes them into a single reading.

## System shape

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│ frontend/  Next.js 14    │  HTTP  │ backend/  FastAPI (intel_    │
│ App Router · TS · Tail-  │ ─────▶ │ platform)                    │
│ wind · d3 +              │  axios │  • Neo4j        (graph)       │
│ leaflet                  │        │  • Postgres/pgvector (docs,   │
└─────────────────────────┘        │    vectors, collection mgmt)  │
                                    │  • Redis + Celery (async)     │
                                    │  • LLMs: Anthropic/OpenAI/    │
                                    │    Cohere/Ollama (orchestr.)  │
                                    │  • crawl4ai + ddgs collection │
                                    └──────────────────────────────┘
```

The frontend is a thin analyst client; all intelligence logic lives in the
backend. The two halves talk over HTTP (axios → FastAPI), and in production a
single container serves both (see [Deployment](#deployment)).

## The intelligence pipeline

SENTINEL is organized around one loop:

**collect** documents from the web → **extract** entities and relationships →
build a **knowledge graph** → **analyze** it through the analyst UI (graph, geo,
timeline, topics, intelligence products).

Each stage maps onto a backend package, and the two datastores each own one half
of the state.

## Backend package map (`backend/src/intel_platform/`)

| Package | Responsibility |
|---------|----------------|
| `api/` | FastAPI app (`api.app:app`) and `routes/` — 24 routers (auth, documents, entities, graph, collections, collection_plans, query, assess, topics, reports, geo, timeline, search, watchlist, personas, snapshots, admin_config, llm, ingest, export, notebook, projects, health). Middleware handles rate-limiting, request-logging, and security headers. |
| `services/` | Business logic: extraction, enrichment, ingestion, graph_builder, graph_rag, hybrid_retrieval, vector_search, document_clustering, topics, assessment, summarization, geocoding, collection_planner, plan_executor, reports, mindmap_export, graph_cache, text_utils. |
| `collection/` | Agentic web collection: `search` (ddgs) → `crawler`/`scraper` (crawl4ai) → `runner`/`executor` (CollectionRunner) → ingest. `agentic.py` is the LLM-driven planner; `tasks.py` runs Celery jobs. |
| `llm/` | Multi-provider layer: `anthropic`, `openai_provider`, `cohere_provider`, `ollama`, plus `embeddings`, the analytic-tradecraft `skills/`, and the **`orchestrator`** — the single source of truth for provider selection. |
| `enrichment/` | Cyber-observable enrichment: `observables` (refang/classify), `base` (provider ABC + registry), `cache` (Postgres cache + rate limiter), `service` (Investigate orchestrator), `hook` (auto-enrich), and keyless `providers/` (dns, geoip, kev, nvd, rdap, certs, email) that egress via `ProxiedClient`. |
| `graph/` | Neo4j access: `schema.py` (`initialize_schema`) and `store.py`. |
| `db/` | Postgres via async SQLAlchemy: `engine.py` (`init_db`) and `models.py`. |
| `models/` | Pydantic v2 domain models: `entities`, `relationships`, `type_hierarchy`, `requests`, `responses`. |
| `connectors/`, `data/`, `mcp/` | External connectors, seed/reference data (type hierarchy, known entities), and an MCP server surface. |

## Dual datastore — and why

SENTINEL deliberately runs two databases because the data has two shapes:

- **Neo4j — the knowledge graph.** Entities and the typed relationships between
  them are inherently a graph, and analysis is graph-native: neighborhood
  expansion, path-finding, community detection. This is also where operational
  state that must survive restarts lives — `Watchlist`, `Snapshot`, `User`,
  `Project`, and collection nodes are all persisted here. Schema (constraints and
  indexes) is created at app startup via `graph.schema.initialize_schema`.

- **Postgres + pgvector — documents and vectors.** Raw documents, their chunk
  embeddings, the enrichment cache, and collection-plan state are relational and
  benefit from `pgvector` similarity search. Tables are created at boot via
  `db.engine.init_db()` (no Alembic migration flow yet — schema is created on
  startup).

Retrieval blends the two: `hybrid_retrieval` and `vector_search` pull candidate
documents from pgvector, while `graph_rag` walks Neo4j for structured context, so
an analyst question is answered against both the text and the graph.

## LLM orchestration

Every model call routes through `llm/orchestrator.py`. This is a hard rule:
provider selection was once duplicated across four modules, and it was
consolidated into the orchestrator so there is exactly one place that decides
which provider and model to use.

- **Provider-agnostic.** Anthropic, OpenAI, Cohere, and Ollama are all
  implemented behind a common interface. The active provider/model comes from
  config (`default_llm_provider` / `default_llm_model`). The code default is
  Anthropic; the shipped `.env.example` and `docker compose` stack default to
  **Ollama + `qwen2.5:14b`** so the platform runs fully local with no cloud keys.
- **Cost/rate isolation.** High-volume work can be routed to a dedicated
  provider so it won't drain a rate-limited cloud key: extraction
  (`EXTRACTION_LLM_PROVIDER`) and bulk collection (`COLLECTION_LLM_PROVIDER`) can
  each be pointed at local Ollama while interactive analysis uses a cloud model.
- **Analytic tradecraft as skills.** `llm/skills/` holds versioned prompt
  templates for structured analysis — source evaluation, hypothesis generation,
  gap analysis, threat assessment, report writing, plus extraction, topic
  naming/summarization, and collection planning. These give the model an analyst
  frame rather than ad-hoc prompts scattered through the code.
- **Embeddings** default to OpenAI (1536-dim), with Cohere and Ollama as
  alternatives.

## Collection & egress

Collection is agentic: given an objective, `collection/agentic.py` plans sources,
`search` (ddgs) finds candidates, and `crawler`/`scraper` (crawl4ai) fetch them,
feeding the extraction pipeline. Two properties matter for a public repo:

- **SSRF guardrail.** `collection/scraper.py` validates URL scheme and host
  before fetching. This check is intentional and must be preserved when editing
  the scraper.
- **Optional egress proxy.** Web-collection and cyber-enrichment egress (crawl4ai,
  ddgs, and the httpx-based connectors) can be routed through a selectable proxy
  — Off / VPN / Tor — chosen at runtime from the admin API and persisted in
  Postgres. **LLM and cloud-API calls always go direct**, never through the
  proxy. The VPN/Tor sidecars run only under the compose `vpn` profile and are a
  local/self-hosted path (gluetun needs `NET_ADMIN` + `/dev/net/tun`, which
  managed hosts like Railway can't grant; Tor works anywhere). Plain
  `docker compose up` doesn't start them.

## Request flow (analyst asks a question)

1. The frontend calls the backend through `lib/api.ts` (axios). Every request
   carries the API key; auth-gated routes also carry a JWT.
2. Middleware runs first: rate-limit → request-logging → security headers.
3. The route handler pulls structured context from Neo4j (`graph_rag`) and
   relevant documents from pgvector (`hybrid_retrieval` / `vector_search`).
4. It composes a prompt using the appropriate `skills/` template and calls the
   model through `llm/orchestrator.py`.
5. The grounded answer (with citations/provenance) returns to the UI — as a
   graph view, a geo layer, a topic mind-map, or a written intelligence product.

Long-running work (crawls, bulk extraction) is handed to Celery/Redis so requests
stay responsive.

## Deployment

- **Local full stack:** `docker compose up` brings up Neo4j (7474/7687),
  Postgres (5432), Redis (6379), Ollama (11434), the backend (8000), and the
  frontend (3000). Extraction is wired to the in-stack Ollama for a
  keys-optional local experience.
- **Production:** a single multi-stage `Dockerfile` builds the Next.js standalone
  server and the Python backend into one image; the entrypoint starts the
  frontend (Node) and the backend (uvicorn) together. Targeted at Railway.
  Neo4j connection binding (IPv6) has bitten deploys before — verify the bolt
  URI/host when changing DB or deploy config.

## Configuration & security

All settings load through `intel_platform.config.Settings` (pydantic-settings);
business logic never reads `os.environ` directly. The full config surface lives
in [`.env.example`](../.env.example). Before any real deployment: set a strong,
non-default `JWT_SECRET` and admin password, and turn on `REQUIRE_SECURE_AUTH`
(which refuses to start with the built-in development defaults). See the
[Security section of the README](../README.md#configuration--security) and the
self-commissioned [code review](./code-review-2026-03-22.md) for the full
hardening picture.
