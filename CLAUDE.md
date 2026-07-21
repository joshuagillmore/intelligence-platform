# Intelligence Platform — Agent Guide

AI-powered intelligence-analyst workbench: **collect** documents from the web →
**extract** entities/relationships → build a **knowledge graph** → **analyze** it
through an analyst UI (graph, geo, timeline, topics, reports).

This file governs **every** agent working in this repo — local sessions and
Claude Code *online* branches alike. Read it first. `backend/CLAUDE.md` and
`frontend/CLAUDE.md` add stack-specific detail for their half.

## Architecture at a glance

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

- **backend/** — Python 3.11, `uv`-managed. Package `intel_platform` (`api/`,
  `services/`, `collection/`, `llm/`, `graph/`, `db/`, `models/`, `mcp/`).
  Details → `backend/CLAUDE.md`.
- **frontend/** — Next.js 14 App Router, TypeScript, npm. Details →
  `frontend/CLAUDE.md`.
- **Dual datastore:** Neo4j is the knowledge graph (entities + relationships);
  Postgres/pgvector holds documents, embeddings, and collection-plan state.
- **Deploy:** Railway (single Dockerfile, `start.sh` runs frontend + backend).
  Local full stack via `docker compose`.

## Repo layout

| Path | What |
|------|------|
| `backend/` | FastAPI app + all intelligence logic (`src/intel_platform/`) |
| `frontend/` | Next.js analyst UI (`src/app/`, `src/components/`, `src/stores/`) |
| `docs/` | Specs, plans, design records (`docs/design/specs`, `/plans`) |
| `docker-compose.yml` | Local full stack: neo4j, postgres, redis, ollama, backend, frontend |
| `Dockerfile`, `start.sh`, `railway.*` | Production build + Railway deploy |
| `.env.example` | Config surface — copy to `.env` (gitignored) |
| `docs/code-review-2026-03-22.md` | Last full review (2026-03-22); see "Known issues" |

## Branching & integration (READ THIS)

The goal is a deployable `main` and few, coherent branches — not PR sprawl.

- **Never commit directly to `main`. Never force-push `main`.** Always branch.
- **Branch naming:** `feat/…`, `fix/…`, `design/…`, `security/…`, `chore/…` for
  local work; Claude Code *online* uses `claude/<area>-<slug>`.
- **One coherent concern per branch** — a feature or a fix, not a one-liner and
  not five unrelated things. Right-sized branches mean few branches.
- **Merge promptly, then delete the branch.** Don't let branches pile up
  (they were up to 9 before this guide — keep it near zero).
- **Ceremony scales to who's driving:**
  - *Your own local, reviewed work* → branch, self-review, merge locally
    (fast-forward or `--no-ff`). No GitHub PR required.
  - *Autonomous online / agent branches* → one review pass before merge; a
    lightweight PR is the natural place since they're already on GitHub.

## Definition of done (before claiming "done" or merging)

Run the checks for whatever you touched — do not assert success without them:

- **Backend:** `cd backend && uv run pytest` **and** `uv run ruff check .`
- **Frontend:** `cd frontend && npm run lint` **and** `npm run build`

If a check fails, it's not done. Report the failure, don't paper over it.

## Running it

**Local full stack (recommended):**
```bash
docker compose up            # neo4j:7474/7687 · postgres:5432 · redis:6379
                             # ollama:11434 · backend:8000 · frontend:3000
```
**Backend alone:** `cd backend && uv run uvicorn intel_platform.api.app:app --reload`
**Frontend alone:** `cd frontend && npm run dev`  → http://localhost:3000

## Config & secrets

- Copy `.env.example` → `.env` (gitignored). **Never commit `.env` or keys.**
  Sensitive: `JWT_SECRET`, `API_KEY`, `POSTGRES_URL`, `NEO4J_PASSWORD`,
  `COHERE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
- Add every new setting to `.env.example` (with a safe placeholder) so the
  config surface stays discoverable.
- Settings load via pydantic-settings (`intel_platform.config.Settings`).

## Conventions

- Keep files focused and boundaries clean; if a file is growing unwieldy, that's
  a signal it's doing too much — prefer a small, targeted split over a pile-on.
- Follow existing patterns before inventing new ones; don't do unrelated
  refactors in a feature branch.
- LLM calls go through the provider **orchestrator** (`llm/orchestrator.py`) —
  don't re-implement provider selection (it was duplicated across 4 modules and
  consolidated; keep it that way).
- Don't add heavy dependencies casually; both halves are already dependency-rich.

## Known issues / watch-outs

- **Auth:** ships with default development credentials — any real deployment
  must set strong, non-default admin credentials and a real `JWT_SECRET` (never
  the `.env.example` placeholder).
- **Watchlists and snapshots are persisted to Neo4j** (`Watchlist` / `Snapshot`
  nodes) and survive restarts. The remaining in-memory state is the admin
  `_llm_override` (provider/model override in `admin_config`), which resets on
  restart — persist it if that matters.
- **Collection scraper** validates URL scheme/host before fetching — preserve
  that validation when editing `collection/scraper.py`.
- **Neo4j on Railway** — connection binding (IPv6) has bitten deploys before;
  verify the bolt URI/host when changing DB or deploy config.

## Don't

- Don't commit to `main`, commit secrets, or force-push shared branches.
- Don't claim done without the verification commands above.
- Don't restructure the codebase without a plan in `docs/`.
