# Verification Gates, Evidence Spans, Cross-Process Telemetry, Admin Ownership — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Four packages in their own worktrees; the lead integrates onto `feat/verification-evidence-telemetry-ownership`.

**Goal:** Protect what has landed (an extraction-quality gate in CI, e2e specs for the flows that only hand-driving caught, a production image that fails closed), finish relationship precision with evidence spans, make degraded counts visible across processes, and stop admin-created projects from sitting open.

**Spec:** the six items agreed on 2026-10-02 after the review follow-ups; `docs/code-review-2026-09-30.md` for background.

## Global constraints

- Branch from `feat/verification-evidence-telemetry-ownership`; never commit to `main`.
- Definition of done unchanged (backend `ruff` + full `pytest` with both databases; frontend `lint` + `build` + `test`). Test database URLs use `127.0.0.1`.
- Routes keep declared response models; packages that change a route regenerate `backend/openapi.json` and `frontend/src/lib/api.generated.ts`.
- Schema changes are Alembic revisions on top of head, reviewed line by line.
- Billed model calls only in the opt-in eval runner; the Cohere key allows 20 calls a minute and 1,000 a month.
- Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01XmtRBmBBfAoEphDqi3e1MX`

## Packages and ownership

| WP | Name | Neo4j | Postgres | Owns |
|---|---|---|---|---|
| V | verification | 7687 | 5435 | `.github/workflows/ci.yml`, `Dockerfile` (the `REQUIRE_SECURE_AUTH` default), `backend/tests/eval/check_against_committed.py` (new), `frontend/tests/e2e/**` (new API-level specs and `global-setup.ts` if needed), `docker-compose.ci.yml`, `backend/CLAUDE.md` and `frontend/CLAUDE.md` (the CI and e2e paragraphs), `SECURITY.md` (the image default) |
| E | evidence-spans | 7691 | – | `services/extraction.py`, `services/graph_builder.py` (edge `evidence` from the span), `llm/skills/**`, `tests/eval/run_corpus_eval.py`, `tests/eval/README.md`, `tests/eval/corpus_eval_*.{json,md}`, `tests/eval/llm_replies.json`, `tests/fixtures/extraction*/**`, their tests |
| T | telemetry-aggregate | 7688 | 5436 | `services/telemetry.py`, `db/models.py` (new table), the Alembic revision, `collection/job_runner.py` and `worker.py` (flushing), `api/routes/{health,admin_config}.py`, `models/responses.py` (the degraded models), `frontend/src/components/DegradedCard.tsx`, `frontend/src/app/admin/page.tsx`, the generated files (regenerate last), their tests |
| O | admin-ownership | 7689 | 5437 | `api/routes/projects.py`, `api/access.py`, `db/members.py`, `frontend/src/app/project/[id]/**`, `frontend/src/app/page.tsx`, `frontend/src/components/ProjectMembersPanel.tsx`, `frontend/src/lib/api.ts` (project calls only), `SECURITY.md` (the ownership paragraph only; V edits a different paragraph), their tests |

No two packages share a file except `SECURITY.md` (different paragraphs) and the generated files (regenerated at integration).

## Cross-package contracts

1. **Eval gate (V reads E's outputs).** `tests/eval/check_against_committed.py --mode <m>` runs `run_corpus_eval.py --mode <m> --replay-only` into a temp dir and compares entity F1, typed F1 and typed-relationship F1 per set against the committed `tests/eval/corpus_eval_<m>.json`; it fails when any number is lower than the committed one by more than 0.005. No thresholds file: the committed results are the baseline, so E's improved results become the baseline when merged. The CI job runs it for nlp, llm and hybrid with no network.
2. **Evidence spans (E).** The `entity_extraction` prompt asks for `"evidence": "<verbatim sentence>"` on every relationship; the parser keeps an edge only if its evidence is a verbatim substring of the source text (whitespace-normalised) and names both endpoints; the span is stored as the edge's `evidence` (already a property) and `evidence_offset`. NLP relationships already come from a sentence; record it the same way. Metric: typed precision in llm and hybrid modes must rise without typed recall falling more than 0.02.
3. **Telemetry rows (T).** Table `degraded_events` (`id`, `process` ("api"|"worker"), `host`, `subsystem`, `reason`, `count`, `window_start`, `window_end`); each process flushes its in-memory counters every 60 s and at shutdown (the worker also at job end). `GET /admin/degraded` returns `{since, processes: {api: {...}, worker: {...}}, total: {subsystem: {reason: count}}}` over the last 24 h from the table plus the API's live counters; `/health.degraded` stays per process. The card shows the combined view with a per-process breakdown.
4. **Admin ownership (O).** A project created by an admin lists the admin as `owner` (contract 1 of the access plan is amended: admins are listed when they create). `POST /projects/{id}/claim` (admin only) adds the admin as owner of an open project and restricts it; 409 if already restricted. `GET /projects` for an admin includes `access` so the list can show "open" projects; the projects page shows a "Claim" control on open projects for admins and a banner when any open project exists.
5. **Fail closed (V).** The root `Dockerfile` sets `ENV REQUIRE_SECURE_AUTH=true`; CI's image job starts the container with no secrets and asserts it exits non-zero with the secure-auth message within 60 s, then starts it with `REQUIRE_SECURE_AUTH=false` for the existing checks. `docker-compose.yml` sets it false explicitly for local use.

## Package task lists

### WP-V verification
1. `check_against_committed.py` (contract 1) with a unit test that a lowered F1 fails and a raised one passes; a CI job `Extraction eval (replay)` in the backend workflow (no databases; `uv sync`, spaCy model, run three modes).
2. API-level e2e specs under `frontend/tests/e2e/` using Playwright's request context against the compose stack: `access.spec.ts` (two analysts registered by the admin; open then restricted on first owner; viewer refused a form-body write; non-member 403 not 404; admin bypass; last-owner 409; project list filtered), `worker-run.spec.ts` (create a plan from a PIR with no LLM available → `generation_failures` present → execute → `queued` → the worker claims it → cancel → `cancelled`), `evidence.spec.ts` (ingest a named document → `GET /entities/{id}/documents` returns a passage), `degraded.spec.ts` (`/health.degraded` and `/admin/degraded` shapes). They must not need an LLM; where a flow would, the spec asserts the honest failure shape instead. Wire the compose stack so the worker runs (it already does in CI).
3. Contract 5 and the SECURITY.md paragraph.

### WP-E evidence-spans
Contract 2; test-first on corpus sentences; one live re-run of llm and hybrid (about 80 calls) after the prompt change; README table extended; a replay check that the committed results reproduce.

### WP-T telemetry-aggregate
Contract 3 with the Alembic revision, flush tests (API and worker), a 24 h window query, and the card.

### WP-O admin-ownership
Contract 4, tests for creation-by-admin, claim, double-claim 409, non-admin claim 403; the projects page banner and control; the SECURITY.md paragraph rewritten (an admin should claim existing open projects, and new admin projects are owned).

## Integration (lead)

Merge E, then T (regenerate the export), then O (regenerate), then V last (its gate must see E's results and its specs the final routes). Full checks; run the new e2e specs against a local stack; merge to `main` and push; no Railway deploy.
