> **Note:** This is a self-commissioned full-codebase review, kept in-repo as a
> record of the audit and the fixes it drove. It was previously at the repo root
> as `CODE_REVIEW_REPORT.md`. Line-item statuses reflect the state at review time;
> a few "Flagged" items have since been implemented (see the Recommendations at
> the end and the current root `CLAUDE.md` for the live status).

# Code Review Report — Intelligence Platform

**Date:** 2026-03-22
**Reviewer:** Claude Opus 4.6
**Repo:** intelligence-platform (Python/FastAPI + TypeScript/Next.js)
**Files reviewed:** 68 backend source files, 34 frontend source files, 15+ config files

## Executive Summary

The Intelligence Platform is a well-structured full-stack application with clear separation between backend (FastAPI/Neo4j) and frontend (Next.js/React). The codebase follows consistent patterns and has good test coverage (48 test files). Key issues found: duplicated LLM provider selection logic across 4 modules, N+1 database query patterns in high-traffic endpoints, unbounded in-memory caches, a hardcoded JWT secret without production safeguards, SSRF risks in the web scraper, and internal error details leaking to API clients. All critical and high-severity issues have been fixed.

## Findings by Phase

| Phase | File | Finding | Severity | Status |
|-------|------|---------|----------|--------|
| 1 | `api/app.py` | Debug routes endpoint exposes internal route info | Medium | Fixed |
| 1 | `api/app.py` | Duplicate `import os` | Info | Fixed |
| 1 | `api/app.py` | Duplicate logging import (`import logging as _logging`) | Info | Fixed |
| 1 | `services/graph_rag.py` | Duplicated LLM provider selection (4 modules) | Warning | Fixed |
| 1 | `api/routes/assess.py` | Duplicated LLM provider selection | Warning | Fixed |
| 1 | `services/topics.py` | Duplicated LLM provider selection | Warning | Fixed |
| 1 | `api/routes/projects.py` | Duplicated `_normalize_datetime` function | Warning | Fixed |
| 1 | `api/routes/geo.py` | Duplicated `_parse_neo4j_datetime` function | Warning | Fixed |
| 1 | `api/routes/ingest.py` | Unused `Optional` import, legacy type syntax | Info | Fixed |
| 1 | `api/routes/snapshots.py` | Unused `Field` import | Info | Fixed |
| 1 | `api/routes/collections.py` | Unused `Field` import | Info | Fixed |
| 1 | `api/routes/geo.py` | Unused `Query` import | Info | Fixed |
| 1 | `api/routes/entities.py` | Overly broad `except (ValueError, Exception)` | Warning | Fixed |
| 2 | `api/routes/projects.py` | N+1 pattern: 3 DB calls per project in list | Critical | Fixed |
| 2 | `api/routes/documents.py` | N+1 pattern: 1 relationship query per document | Critical | Fixed |
| 2 | `api/routes/graph.py` | Double graph fetch (display + NetworkX build) | Warning | Fixed |
| 2 | `services/graph_rag.py` | Unbounded DB queries in `understand_query` (~20 queries per call) | Warning | Fixed |
| 2 | `api/routes/geo.py` | Double `get_entity` call per relationship in timeline | Warning | Fixed |
| 2 | `services/topics.py` | Unbounded `_summary_cache` (grows forever) | Warning | Fixed |
| 2 | `api/cache.py` | Unbounded `_cache` dict (grows forever) | Warning | Fixed |
| 2 | `api/routes/snapshots.py` | Unbounded `_snapshots` dict (grows forever) | Warning | Fixed |
| 3 | `api/auth.py` | Hardcoded JWT secret with no production warning | High | Fixed |
| 3 | `api/app.py` | SSRF via path traversal in frontend proxy | High | Fixed |
| 3 | `collection/scraper.py` | SSRF: no URL scheme/host validation in web scraper | High | Fixed |
| 3 | `frontend/lib/api.ts` | Hardcoded fallback API key in healthApi | Medium | Fixed |
| 3 | `api/routes/auth.py` | No input validation on registration (password, role) | Medium | Fixed |
| 3 | `api/routes/entities.py` | No validation on entity type update value | Medium | Fixed |
| 3 | `services/graph_rag.py` | Internal error details leaked to API client | Medium | Fixed |
| 3 | `api/routes/assess.py` | Internal error details leaked to API client | Medium | Fixed |
| 3 | `.env.example` | Missing LLM provider config template | Info | Fixed |
| 3 | `api/auth.py` | Default admin credentials (in-memory user store) | Medium | Flagged |
| 3 | `api/routes/watchlist.py` | In-memory watchlist lost on restart | Info | Flagged |
| 3 | `api/routes/snapshots.py` | In-memory snapshots lost on restart | Info | Flagged |

## Flagged Items

Items marked with `SECURITY`, `PERF`, or `REVIEW` comments that need human decision:

1. **`api/auth.py` — Default admin credentials**: The in-memory user store with a default admin account is acceptable for a single-user workbench but should be replaced with a database-backed user store before any multi-user or production deployment. See `# Change in production!` comment.

2. **In-memory state stores** (`_snapshots`, `_watchlists`, `_llm_override`): These are lost on container restart. Consider persisting to Neo4j (like Collections already does) if data persistence matters.

3. **`config.py` — `spacy_model` default mismatch**: Config defaults to `en_core_web_lg` but Dockerfile installs `en_core_web_sm`. The fallback in `extraction.py` handles this, but it should be aligned.

4. **`api/middleware.py` — Rate limiter per-IP tracking**: The `defaultdict(list)` rate limiter stores timestamps per IP. In a reverse-proxy setup, all requests may share the same IP. Consider `X-Forwarded-For` header if deployed behind a load balancer.

## Metrics

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 3 |
| Warning | 10 |
| Medium | 7 |
| Info | 8 |
| **Total** | **30** |

| Status | Count |
|--------|-------|
| Fixed | 27 |
| Flagged for Review | 3 |

## Recommendations

1. **~~Persist in-memory state to Neo4j~~** — **Implemented**: Watchlists and snapshots now stored as Neo4j nodes (`Watchlist`, `Snapshot`). Data survives container restarts.

2. **~~Add request-level logging middleware~~** — **Implemented**: `RequestLoggingMiddleware` logs `IP METHOD /path STATUS DURATIONms` for every request.

3. **~~Pin dependency versions more tightly~~** — **Implemented**: All `pyproject.toml` dependencies changed from `>=` to `~=` (compatible release).

4. **~~Add a health check for Ollama connectivity~~** — **Implemented**: `/health` now returns `ollama_connected` field. Status is `degraded` when Ollama is the default provider but unreachable.

5. **~~Database-backed user management~~** — **Implemented**: Users stored as Neo4j `User` nodes. A default admin account is created on first startup if no users exist. Registration creates new `User` nodes.
