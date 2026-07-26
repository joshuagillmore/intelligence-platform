# 15-run PIR campaign — findings

**Date:** 2026-07-26 · **Method:** fifteen full analyst runs, each a distinct
requirement — PIR → LLM refinement → EEI capture → collection plan → live crawl
→ hybrid extraction → knowledge graph → **satisfaction assessment** → written
intelligence product.

Runs deliberately vary along three axes so the system is not exercised on one
shape of problem:

| Axis | Spread |
|---|---|
| Domain | cyber (6), maritime, sanctions, conflict (2), supply chain, WMD, disinformation, economic, geopolitics |
| Geography | Ukraine, South China Sea, Russia, Sahel, DPRK, Taiwan, Middle East, Arctic, Europe, Iran, francophone Africa, Red Sea, DRC, global |
| Source budget | 3 – 7 (not the fixed 5 used previously) |

Follows `findings-2026-07-26-pir-loop.md`, which this campaign was designed to
stress beyond a single domain.

---

## 1. The headline: PIRs can now report whether they were answered

`Pir.eeis` and `PirStatus.PARTIAL/SATISFIED` had existed since the requirements
spine was built, and **nothing ever wrote either**. The refinement generated
Essential Elements of Information and discarded them; status never left `OPEN`.
A PIR therefore could not report whether collection had answered it — the
analyst got a pile of documents and was left to infer it.

Built this campaign (`POST /api/pirs/{id}/assess`):

- **EEI capture** — the elements the refinement already produces are persisted
  onto the PIR, giving satisfaction something to measure against.
- **Per-element judgement** — each EEI is judged against the project's own graph
  (entities plus relationship evidence), explicitly *not* the model's background
  knowledge, and returns SATISFIED / PARTIAL / UNMET with a justification.
- **The stop condition** — `stopped_on_source_limit` distinguishes *"the
  requirement is answered"* from *"collection ran out of sources with these
  elements outstanding"*, and `unmet_criteria` names what is still missing.

Live output, run 2 (South China Sea, budget 6, 5 used):

```
status PARTIAL — 0/4 EEIs fully satisfied, 168 entities
[PARTIAL] Call signs or hull numbers of militia and coast guard vessels
          :: hull numbers CCG 21581, CCG 3107, and Chinese Maritime Militia…
[UNMET]   Dates and times these vessels were active near Second Thomas Shoal
          :: no dates or timestamps present in the collection
[PARTIAL] Resupply-interdiction tactics used against Philippine vessels
          :: documents water-cannon attacks and towing-rope tactics by CCG 3107…
[UNMET]   Frequency and duration of each interdiction event
          :: lacks frequency counts or duration measurements
-> 4 element(s) still unanswered and collection budget remains (5/6 sources)
   — continue collection.
```

That is the intended behaviour end to end: real specifics found, real gaps
named, and a recommendation that distinguishes "keep collecting" from "budget
spent". A failed judging call leaves the stored status untouched rather than
silently reopening a satisfied requirement.

---

## 2. Defects found and fixed during the campaign

Every one of these was found by running real requirements, not by inspection.

### 2.1 EEI capture produced unusable criteria (three distinct forms)

The criteria drive the assessment, so junk in means junk verdicts.

| Observed | Cause | Effect |
|---|---|---|
| `EEI 3: Specific ICS devices…` | model double-labels (`3. EEI 3: …`); the outer marker was consumed, the inner survived | label text inside the criterion |
| `Initial Access Vectors:** Determine…` | `**bold**` mid-string survived a leading/trailing strip | markup in the criterion |
| `Refined PIR:` | a section label captured as if it were a criterion | **unsatisfiable** — assessed and reported unmet forever |
| `The refined version provides a clearer focus…` | the model's commentary about its own rewrite | **unsatisfiable** — collection can never answer it |

The last two matter most: a criterion collection cannot possibly satisfy blocks
`SATISFIED` permanently. Consolidated into `_clean_eei`, which drops headings
and refinement commentary rather than assessing them.

### 2.2 Verdicts were parsed by shape, and the model changed shape

`command-a-plus` prefixes `EEI_ASSESSMENT:` to *every* verdict line rather than
emitting it once as a header. The parser anchored on a leading digit, missed all
three lines, and a fully-judged PIR reported *"assessment unavailable"*.

A missed verdict is indistinguishable from an unassessed requirement, so the
matcher is now permissive about labelling and strict about the three fields.
Parsing moved into `parse_verdicts` so tests exercise the real function — the
previous tests re-declared the regex and would have passed while the code drifted.

### 2.3 The judge was shown an alphabetical sample of the graph

**Severity: high — it produced false negatives.** `search_entities` orders by
name, so a head-slice handed the model an arbitrary alphabetical window. On the
ransomware run that meant **400 entities considered, the six ThreatActor and
four Campaign nodes never shown**, and the requirement reported as having no
supporting evidence at all. The collection was fine; the sampling was not.

Crawled pages also yield very large numbers of `URL` and bare `Domain` nodes —
41% of one run's graph — which are legitimate content but answer no requirement
and crowded out the entities that do. They are now excluded from the judging
window (not from the graph), evidence is deduplicated, and the window is wider.

Measured on the same collection: 1 of 3 elements judged → 3 of 3, with
justifications citing collected specifics — *"lists multiple initial access
vectors for Akira but does not specify preferred vectors per group"*.

### 2.4 PARTIAL progress was stored as OPEN

Only `SATISFIED` counted toward progress, so a PIR with two PARTIAL elements
was persisted as `OPEN`. That erases the distinction between "we have something
on this element" and "we have nothing" — which is exactly what decides whether
the next cycle re-collects or refines the requirement.

---

## 3. Found, not fixed — recommended work

### 3.1 Extraction emits no telemetry, and a dead run is indistinguishable from a busy one

**Severity: high.** Two problems that compound:

- The last event emitted is `url_fetched`. Extraction then runs for **10+
  minutes with no events at all** — measured on run 1: last event 17:23:58, work
  continuing past 17:35.
- `execution-status` derives `running` from the *absence* of a terminal event.
  A backend restart mid-collection leaves the plan reporting `running` **forever**
  (confirmed directly: restarting the backend killed an in-flight collection and
  the plan still reported `running` with a frozen `updated_at`).

Together these mean an analyst watching the Trace view cannot tell "extracting"
from "dead", and a crashed collection never surfaces as failed. It also cost
this campaign a wasted run: a 6-minute stall threshold assessed run 1 before its
graph existed, reporting 0 entities when 245 landed shortly after.

**Proposal:** emit per-document extraction events (`doc_extracting` /
`doc_extracted` with entity counts), and add a heartbeat plus a liveness check
so a plan with no event for N minutes and no owning task reports `stalled`
rather than `running`. This is the single highest-value fix found.

### 3.2 Three in five sources fail, and most of them never could have worked

**Severity: high — this is the largest single constraint on answer quality.**
Measured across the campaign: **41 source failures against 27 successes.**

| Failure class | n | What it means |
|---|--:|---|
| Endpoint does not exist (404) | 10 | planner invented the URL |
| RSS feed returns non-XML | 8 | planner invented a feed URL; the page is HTML |
| Auth required / bot-blocked (401, 403) | 8 | Shodan, AlienVault OTX, MarineTraffic — real sources, no credentials |
| Other | 9 | |
| Fetched but yielded nothing | 4 | |
| Upstream unavailable (503) | 2 | genuinely transient |

Roughly **two thirds of failures are sources that could never have succeeded**:
a hallucinated URL, or a real service the platform has no key for. Only the 503s
are bad luck. The planner is asked to name sources and does so plausibly, with
nothing checking that the thing it named exists or is reachable.

This compounds with §3.1: a run that loses 2 of 3 sources still ends `completed`
and the analyst is not told the collection was substantially degraded — they
just see fewer answered EEIs.

**Proposal, in order of value:**

1. **Validate at plan time.** A cheap HEAD/GET on each generated source before
   the plan is committed, with content-type checking for feeds. A dead source
   should be visible while the plan is still a draft an analyst can edit, not
   discovered at execution.
2. **Only propose what is reachable.** Give the planner a registry of connectors
   that are actually configured with credentials, and let it mark a source as
   *desirable but unavailable* rather than emitting a config that will 401. The
   previous document's finding 2.6 predicted exactly this; it is now quantified.
3. **Fail feeds honestly.** An HTML page fed to the RSS parser should report
   "not a feed" rather than `not well-formed (invalid token)` at line 13.
4. **Surface degradation.** A plan that completed with a majority of sources
   failed should say so in its terminal state, not just in per-source rows.

### 3.3 EEIs are demanding in a way collection cannot meet

The refinement produces genuinely rigorous elements — *"identified by IMO
numbers"*, *"call signs or hull numbers"*, *"frequency and duration of each
event"*. This is good tradecraft and bad calibration against a 2–7 source web
crawl: most runs return UNMET on most elements not because collection failed but
because open web reporting does not carry that specificity.

**Proposal:** have the refinement mark each EEI with a realistic collection
source type (OSINT / commercial / classified-equivalent), and let the assessor
report "not answerable from the sources planned" separately from "not collected".
An element no available connector can satisfy is a *collection gap*, not an
analytic failure, and conflating them makes the system look worse than it is.

### 3.4 Entity hygiene, again and at scale

Confirmed across every run, not just cyber: `URL` and `Domain` nodes dominate
crawled graphs (69 of 168 entities on run 2). §2.3 works around this for the
assessor only — the graph view, Graph-RAG retrieval, and products all still see
it. This re-raises finding 2.3 of the previous document with quantified impact.

### 3.5 `ollama_connected` reports false while Ollama is in active use

`/health` only probes Ollama when it is the *default* provider. This deployment
routes **collection** to Ollama and generation to Cohere, so the field reads
`false` while Ollama is doing all the extraction work. Cosmetic, but it is a
health endpoint asserting something untrue.

---

## 4. What held up

- **Planner source selection is strong outside cyber.** Lloyd's List
  Intelligence and the Ukrainian government shadow-fleet tracker for sanctions;
  CSIS Asia Maritime Transparency Initiative for the South China Sea; New Lines
  Institute for the Sahel. The 1.1 fix from the previous campaign is holding.
- **The vessel/platform typing fix works on live data** — run 2 produced `Ship`
  and `Aircraft` nodes from crawled maritime reporting, the exact case that
  previously collapsed to `Custom`.
- **Assessment justifications are grounded.** They cite what was actually
  collected and name what was not, rather than restating the question.
