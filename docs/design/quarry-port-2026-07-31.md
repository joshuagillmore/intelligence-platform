# Porting Quarry's collection loop into Sentinel

**Date:** 2026-07-31
**Source:** `C:\Users\user\Claude\crawl4ai-quarry` (Flask, SQLite, single-user)
**Merged to `main`:** `b7310568`, `28e59116`, `b6377d22`, `01802555`, `49fbb7a5`

## The one difference that mattered

Everything else here follows from a single structural difference.

**In Quarry, assessment is a controller. In Sentinel it was a report.**

Quarry's mission loop (`agent_runner.py:122`) runs passes over *pending*
requirements: search → crawl → `assess_requirement` → write the assessor's
`next_queries` back onto the requirement → next pass. It stops when every
requirement is `satisfied` or `unmet`. The assessor's output *is* the next query.

Sentinel assessed once, after collection had already finished. The 15-run
campaign ended runs with verdicts like:

```
PARTIAL 1/4 EEIs satisfied
  -> 3 element(s) still unanswered and collection budget remains (1/6 sources)
     — continue collection.
```

Nothing continued it. The verdict had no actuator. Sentinel's agentic loop does
carry a `satisfied` field, but `agentic.py` grades *a source's own contribution
to the PIR* — did this document do its job — not whether an element of the
requirement is answered. That question cannot drive re-tasking.

## What was ported

### 1. Multi-engine search (`b7310568`)

Quarry's `search.py` records the measurement plainly: the duckduckgo backend
returns "no results" under light load for queries brave and bing serve in under
a second.

That failure was silent in Sentinel, which was ddgs-only. A run whose search
returns nothing acquires nothing and still completes; the plan reports success
and the analyst sees an empty graph with no error. Campaign totals: **41 source
failures against 27 successes**, most of them sources that never resolved.

`web_search` now walks `SEARCH_BACKENDS` (default `auto,brave,bing,duckduckgo`)
and the first engine to return anything wins. The proxy is passed to *every*
engine — collection egress goes through the VPN/Tor tunnel and a fallback that
bypassed it would leak.

### 2. Per-requirement state and the closed loop (`28e59116`)

`pir_requirements` gives each EEI somewhere to hold state: `status`
(pending/satisfied/unmet), `attempts`, `next_queries`, `assessment_missing`,
`assessment_confidence`. `Pir.eeis` stays the source of truth for the criteria
*text* — every existing consumer reads it — and these rows carry the state that
text acquires. Re-wording an element resets its state, because a reworded
element is a different question.

`requirement_assessor.assess_requirement()` answers the narrower question a loop
can act on, grounded in the project's own chunks and graph.

`requirement_loop.run_requirement_passes()` re-tasks at what the planned sources
left open. **Three stopping conditions, each reported as itself:**

| Condition | Meaning |
|---|---|
| all elements resolved | the requirement is answered |
| element retired | tried `attempts_per_element` times and given up on — *not* the same as untried |
| source / pass budget | stopped short, elements still open |

An exhausted run is never reported as a satisfied one.

### 3. Persona-driven decomposition (`b6377d22`)

Quarry builds a persona from an area of expertise and runs the *planner* under
it. Sentinel had a personas subsystem that reached nothing that mattered:
`persona` appeared nowhere in `collection_planner.py` or `pirs.py`.

Which elements a requirement is split into decides what gets collected, so that
is where expertise has to apply. `refinement_system_prompt()` now opens with the
active persona's framing and uses its temperature.

### 4. One content-quality gate (`01802555`)

Quarry's `content_quality.py` exists because a "successful" crawl is often a
captcha wall. Sentinel caught login and paywall pages but nothing else.

`rejection_reason()` returns *why* a page was rejected, applied before it can
spend a source from the budget, and the reason reaches the activity trail — a
site that blocked us and a site that had nothing both arrive as "0 documents"
otherwise.

### 5. Making it visible (`01802555`, `49fbb7a5`)

`GET /pirs/{id}/requirements` and a requirement matrix on the PIR panel. Without
these the loop's decisions would be another feature with no consumer — the exact
criticism that applies to the PIR assess endpoint, which still has no frontend
caller.

## Deliberately not ported

- **The editable approval gate.** Quarry's mission page *is* the plan: the DOM
  serializes back into `plan_json` on submit. Sentinel's collection flow has no
  equivalent surface, so porting this means designing new UI rather than moving
  code. Left as a decision.
- **In-memory job store, single-worker gunicorn, SQLite, no auth.** Deliberate
  Quarry simplifications that would be regressions here.

## Defects found while porting

- A 380-word article *mentioning* captchas was rejected as an interstitial by
  the ported rule. An interstitial is by construction a page with nothing on it,
  so a marker now condemns a page only in the title, or when the page is also
  too thin to be an article. Without this a cyber requirement would have
  silently discarded exactly the reporting it wanted.
- `labelled_json` required the JSON object on the label's own line — the shape
  the prompt asks for, not reliably the shape that comes back. Added
  `json_object()`, which scans for a brace-balanced object anywhere in a reply,
  ignoring braces inside strings.

## What this does not fix

Source *quality* remains the limiting factor. The loop can now ask better
questions, and multi-engine search means a query is more likely to return
something — but nothing here validates that a proposed source could ever have
answered the requirement. Plan-time source validation (findings §3.2) is still
unbuilt.
