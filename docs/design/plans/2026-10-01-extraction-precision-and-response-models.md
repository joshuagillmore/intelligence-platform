# Extraction Precision and Response Models — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Two packages in their own worktrees; the lead integrates onto `feat/extraction-precision-and-response-models`.

**Goal:** Close the three open items left after the 2026-10-01 hardening: relationship precision in extraction, the NLP gaps, and the API operations that declare no response model (so the generated client types cover the whole contract).

**Spec:** `docs/code-review-2026-09-30.md` ("Adjustments executed", row "Still open") and `backend/tests/eval/README.md` (the per-mode tables and the "Not fixed" notes).

## Global constraints

- Branch from `feat/extraction-precision-and-response-models`; never commit to `main`.
- Definition of done unchanged (backend `ruff` + full `pytest`; frontend `lint` + `build` + `test`). Test database URLs use `127.0.0.1`.
- Billed model calls only in the opt-in eval runner. The Cohere trial key allows 20 calls a minute and 1,000 a month; a full llm+hybrid run over the three corpora is about 160 calls, so re-run live only when the prompt changes, and replay recorded replies otherwise.
- No behaviour change in the response-model package beyond declaring what the routes already return; a declared model that would reject today's real responses is a bug in the model, not a reason to change the route.
- Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01XmtRBmBBfAoEphDqi3e1MX`

## Packages and ownership

| WP | Name | Neo4j | Postgres | Owns |
|---|---|---|---|---|
| E | extraction-precision | 7691 | – | `services/{extraction,text_utils,graph_builder}.py`, `llm/skills/**`, `data/*.yaml`, `tests/eval/**`, `tests/fixtures/extraction*/**`, their tests |
| M | response-models | 7688 | 5436 | `api/routes/**` (only `response_model=` declarations and the Pydantic models they need), `models/responses.py` (new models), `backend/openapi.json`, `frontend/src/lib/{api.ts,apiTypes.ts,api.generated.ts}` and the frontend files that consume types from them, their tests |

The two packages share no file.

## WP-E extraction-precision

Measured on `openrep-deep` (hybrid, 722 model relationships): 230 generic associations, 122 event→date links, 66 edges to entities the model never listed; gold labels none of those. Tasks, each test-first on a corpus sentence and each moving a number in `tests/eval/README.md`:

1. **Scoring decision, made explicit.** Event→date links feed the timeline and are legitimate; score them separately. The runner reports relationship metrics twice: `typed` (excluding `ASSOCIATED_WITH` and `OCCURRED_ON`/date links) and `all`. Gold stays as it is. The README states the rule.
2. **Generic associations.** An `ASSOCIATED_WITH` edge is emitted only when the sentence contains both entities and no typed relation was found between them; the model prompt says the same and gives a negative example. Measure the drop in generic edges and the effect on `typed` recall (it must not fall).
3. **Endpoints must be listed entities.** The `entity_extraction` prompt requires every relationship endpoint to appear in the entity list; the parser drops an edge whose endpoint is not listed *and* not resolvable to a listed entity by the hybrid alias rule, counting it under `relationships_dropped_by_reason.unlisted_endpoint` in the extraction result (the graph build keeps its own count for what reaches it).
4. **Government ↔ country.** When one pass names a government ("PRC government", "the Kremlin", "Tehran" as actor) and another the country, resolve to the country node with the government form kept as an alias. A small, explicit table in `data/` (country ↔ government forms ↔ capital-as-metonym), applied in the hybrid merge and in `graph_builder` resolution.
5. **NLP gaps.** Acronyms that are proper names (JCPOA, NDAA, INDOPACOM) are kept; name fragments cut from headings ("Assess Russian hybrid warfare" → no entity "Assess Russian") are rejected by a heading-aware filter (a line that is all title-case or ends without a full stop and starts with an imperative is a heading).
6. Re-run the three modes once with live Cohere **after** the prompt change (the recorded replies no longer apply), commit results, and extend the README tables.

## WP-M response-models

1. For each of the 142 operations without `response_model`, declare one. Reuse existing models in `models/responses.py`; add new ones there, named `<Thing>Response` / `<Thing>Item`. Prefer `extra="allow"` only where a route genuinely returns open-ended dicts (document properties, enrichment payloads), and say so in the model's docstring. Fields that today are sometimes absent become `Optional` with `None`; do not change what the route returns.
2. Prove no behaviour change: a test that calls every GET operation with a seeded project through the TestClient and asserts the response validates against its declared model, plus the existing suite. `uv run python scripts/export_openapi.py` and commit the file.
3. Frontend: `npm run gen:api`; replace every hand-written interface in `api.ts` that now has a declared model with `ResponseOf<...>`; delete the `Undeclared` fallback where no longer needed; fix any mismatch the types reveal and list them. Lint, build, unit tests.
4. Report: how many operations now declare a model (must be 156 of 156), the mismatches found, and any model that needed `extra="allow"`.

## Integration (lead)

Merge E, then M (M regenerates nothing from E; if E changes a route-visible shape, which it should not, the lead re-exports). Full checks, then merge to `main` and push; no Railway deploy.
