# Multi-Agent Orchestration Setup — Design Record

**Date:** 2026-07-18
**Status:** Facet 1 (Foundation) implemented; facets 2–5 planned.
**Repo:** intelligence-platform

## Goal

Give the Intelligence Platform a deliberate **multi-agent development
environment**: a shared "brain" every agent (local sessions and Claude Code
*online* branches) reads, a disciplined branch/merge workflow, defined agent-team
roles, a documentation spine, and a home for the coming frontend (Sentinel)
work.

## Context that shaped the design

- **A fleet is already running.** ~9 `origin/claude/*` branches existed
  (analyst-UX, collection pipeline, deploy, entity-extraction, graph-intelligence,
  reviews…) — Claude Code online was already producing branches, but they were
  **piling up unmerged**. Taming that sprawl is a primary driver.
- **`main` had ungoverned WIP** (13 uncommitted files) — deferred to a separate
  cleanup step (facet 2), not touched here.
- **Two distinct toolchains:** `uv`/Python/FastAPI backend and npm/Next.js
  frontend → argues for nested, scoped guidance rather than one big file.

## The five facets (and order)

| # | Facet | Status |
|---|-------|--------|
| 1 | **Foundation** — repo-rooted `CLAUDE.md` + scoped backend/frontend files + `.claude/` permissions | **Done (this doc)** |
| 2 | **Branch & integration workflow** — review→merge→clean the `claude/*` sprawl; triage the dirty `main` tree | Next |
| 3 | **Agent teams** — `.claude/agents/` roles (backend, frontend, collection, graph, reviewer, docs) | Planned |
| 4 | **Docs spine** — architecture / runbooks / decision records under `docs/` | Planned |
| 5 | **Frontend (Sentinel)** — the paper/ink redesign work stream, governed by 1–4 | Planned |

## Decisions

- **Nested `CLAUDE.md`.** Root governs platform + orchestration; `backend/` and
  `frontend/` hold toolchain specifics. Claude Code loads root + nearest-up, so
  each agent gets focused context. (Alternatives considered: single root file —
  grows large, mixes concerns; thin file + docs manual — weaker at steering
  agents since `CLAUDE.md` auto-loads and `docs/` doesn't.)
- **Branch policy:** never commit to `main`; one coherent concern per branch;
  merge promptly and delete; ceremony scales — local reviewed work merges
  directly, autonomous/online branches get one review pass (lightweight PR). Aim:
  few branches, no sprawl, deployable `main` — not a PR per change.
- **Permissions committed** (`.claude/settings.json`) so online agents inherit
  the same allowlist; sharp edges (`rm`, hard reset, Railway deploy) prompt;
  force-push denied.
- **Dirty `main` tree deferred** to facet 2.

## Facet 1 — what was built

- `CLAUDE.md` (root) — architecture map, repo layout, **branching & integration
  rules**, definition-of-done (backend `uv run pytest`+`ruff`, frontend
  `npm run lint`+`build`), run/deploy, secrets, conventions, known issues.
- `backend/CLAUDE.md` — `uv` commands, package map (api/services/collection/llm/
  graph/db/models), Neo4j+Postgres, LLM orchestrator rule, async/Pydantic-v2
  conventions.
- `frontend/CLAUDE.md` — npm/Next.js 14 App Router, components/stores/lib map,
  zustand+zundo, d3/leaflet, Tailwind tokens, Sentinel-redesign branch note.
- `.claude/settings.json` — shared permission allowlist.

Delivered on branch `chore/claude-foundation` (dogfooding the branch rule).

## Next (facet 2 — branch & integration workflow)

Triage the ~9 `claude/*` branches (merge / rebase / drop), decide the dirty-`main`
WIP, and codify a lightweight review→merge→delete loop (optionally a
`.claude/` command or a scheduled cleanup).
