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

### Campaign results

All fifteen runs completed: plan, collection, graph, assessment and a written
product. Every PIR was re-assessed at the end against the final code, so the
table is one consistent measurement rather than a mix of pre- and post-fix runs.

| # | Domain | Budget | Used | Status | EEIs met | Entities | Product |
|--:|---|--:|--:|---|--:|--:|--:|
| 1 | cyber (Ukraine) | 3 | 5 | OPEN | 0/5 | 245 | 7k |
| 2 | maritime (S China Sea) | 6 | 5 | PARTIAL | 1/4 | 256 | 13k |
| 3 | cyber (financial) | 4 | 4 | OPEN | 0/3 | 571 | 12k |
| 4 | sanctions (shadow fleet) | 7 | 5 | PARTIAL | 3/5 | 432 | 8k |
| 5 | conflict (Sahel) | 5 | 3 | OPEN | 0/4 | 217 | 9k |
| 6 | cyber (DPRK crypto) | 4 | 5 | PARTIAL | 0/5 | 600 | 10k |
| 7 | supply chain (Taiwan) | 6 | 5 | PARTIAL | 3/4 | 96 | 8k |
| 8 | cyber (Iranian OT) | 3 | 4 | OPEN | 0/3 | 167 | 11k |
| 9 | geopolitics (Arctic) | 5 | 5 | OPEN | 0/5 | 600 | 10k |
| 10 | cyber (Salt Typhoon) | 4 | 5 | PARTIAL | 1/4 | 600 | 10k |
| 11 | WMD (Iran) | 6 | 5 | PARTIAL | 0/4 | 380 | 8k |
| 12 | disinformation (Africa) | 5 | 5 | PARTIAL | 1/5 | 484 | 10k |
| 13 | cyber (edge devices) | 3 | 3 | OPEN | 0/3 | 504 | 8k |
| 14 | conflict (Red Sea) | 7 | 5 | PARTIAL | 0/5 | 414 | 7k |
| 15 | economic (DRC cobalt) | 5 | 4 | PARTIAL | 1/5 | 213 | 8k |

**9 PARTIAL, 6 OPEN, 0 SATISFIED — and that is the honest answer.** Two to five
web sources do not fully answer requirements written to this standard ("identified
by IMO numbers", "frequency and duration of each event"). The system's value here
is that it *says so per element* instead of presenting a document pile as an
answer. Zero elements were left unjudged after the second-pass fix (§2.6).

Assessments across re-runs vary by roughly ±1 element on the same graph — the
judge is an LLM at temperature 0.2, and PARTIAL/UNMET is a genuine borderline on
thin evidence. Worth knowing before treating a single score as authoritative.

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

### 2.4 The product did not know what question it was answering

**Severity: high — this was the worst output of the campaign.**
`POST /reports/generate` took `entity_ids` and no requirement. It built both its
retrieval query and its subject from the entity list, so the product answered
"tell me about these entities" rather than the PIR that drove the collection.

The Iranian water-utility OT run passed in entities that included crawled site
furniture. The product it produced:

> **Subject:** EPA Web Ecosystem, Multilingual Support, CISA Water-Sector
> Assistance, and Potential Cyber Exposure
>
> 2. *EPA provides language support in at least 12 non-English languages…* —
>    **Likely**
> 3. *EPA's site aggregates 32 distinct events/topics (e.g., Air, Bed Bugs,
>    Chemicals…)* — **Almost Certain**

A language selector and a topic menu, written up as intelligence judgements in
ICD 203 probability language, for a requirement about PLC and HMI compromise.

`requirement` (or `pir_id`) now leads retrieval and is stated to the writer as
the subject, with supplied entities demoted to candidate evidence that is known
to contain web furniture. Same graph, same entities, regenerated:

> **Subject:** Iranian-Linked Groups Targeting Water and Wastewater Utility
> Operational Technology
>
> Iranian-affiliated cyber actors have compromised water and wastewater utility
> operational technology… The advisory confirms that OT systems were targeted,
> but the collected evidence does **not** specify the exact PLC or HMI devices
> exploited, nor does it provide detailed defensive mitigations.

It now answers the requirement and states the gap, instead of finding something
confident to say about whatever was collected.

### 2.5 A requirement was declared answered on one verdict out of five

**Severity: high.** `unmet` was computed only over elements the model actually
returned a verdict for. An Arctic requirement with five EEIs came back with one
verdict, and the PIR was stored `SATISFIED` — *"Requirement answered across all
elements"* — with four elements never judged at all. Silence read as success.

Unjudged elements are now explicit `UNASSESSED` entries that count against
satisfaction and appear in `unmet_criteria`. Re-run on the same data: a false
`SATISFIED (1/5)` became an honest `PARTIAL (1/5)` naming the four outstanding
elements. A separate flag preserves the original guarantee that a total judging
failure leaves the stored status untouched.

### 2.6 The judge skipped elements, so they went unjudged

Separate from §2.5 (which stopped silence reading as success), models routinely
returned fewer verdicts than there were elements — one of five on the DRC
requirement. Reporting four elements as `UNASSESSED` is honest but tells the
analyst nothing about whether collection answered them.

When a first pass judges some but not all elements, the unjudged ones are now
put to the model again on their own. Verified on that run: 1 of 5 judged became
5 of 5, each citing collected specifics. Across the final re-assessment of all
fifteen requirements, **no element was left unjudged**.

### 2.7 The timeline was an ingestion log, not a chronology

**Severity: high — it disabled one of the four analyst views.** The timeline
sorts by `Event.event_datetime` and falls back to ingestion time. Across the
campaign, **2 of 6,221 entities carried an `event_datetime`**, so a project's
380 "events" were all stamped with the instant the crawl wrote them. For a
temporal view, that is the whole value gone.

The linking code (`_link_event_dates`) was correct. Its input was not:

| | measured |
|---|---|
| `OCCURRED_ON` edges | 22 of 2,418 relationships (0.9%) |
| `Event` nodes | 138, none dated |
| `Date` nodes | 300, extracted but unattached |

Two causes, both invisible:

1. Models name the event **only in the relationship** — `"MV Northern Star
   strike" OCCURRED_ON "12 March 2026"` with no such entity — and
   `graph_builder` then dropped the edge for a missing endpoint, silently.
2. The edge is emitted in either direction about equally.

`_link_event_dates` now orients the edge and recovers the event as an `Event`
entity when it exists only as an endpoint. Narrow by construction: only an
`OCCURRED_ON` edge whose other endpoint is a real `Date` can create anything.

Prompt changes alone did not fix this on `qwen2.5:14b` — worth recording, since
the polarity fix earlier in this project *was* achievable with prompt plus
example. Measured on maritime prose: **0 dated events → 3**, each with a date
parsed from the source text.

`graph_builder` now also counts and logs dropped relationships and filtered
entities. A build that discards a third of its edges previously looked identical
to one that never produced them, which is precisely how this hid.

### 2.8 PARTIAL progress was stored as OPEN

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

### 3.4 Off-topic sources succeed, and nothing notices

The failure taxonomy above counts sources that error. A quieter problem is
sources that fetch cleanly and are simply about something else. The edge-device
CVE requirement collected a **Bulgarian personal-blog directory**, putting
entities like *"Блогът на Делян Делчев"*, *"Кътчето на Селин"* and *"татко
Крокодил"* into the graph as `Custom`, `Campaign` and `Technology` nodes.

Nothing in the pipeline scores a document for relevance to the requirement
before extraction. A successful-but-irrelevant source is more expensive than a
failed one: it consumes budget, costs a full extraction pass, and permanently
pollutes the graph that later retrieval and products draw on.

**Proposal:** score each fetched document against the PIR before extraction
(the agentic loop already asks the model to evaluate results *after* the fact —
this is the same call, moved earlier and used as a gate), and record rejected
documents as `source_irrelevant` so the trail shows why the budget was spent.

### 3.5 Entity hygiene, again and at scale

Confirmed across every run, not just cyber: `URL` and `Domain` nodes dominate
crawled graphs (69 of 168 entities on run 2). §2.3 works around this for the
assessor only — the graph view, Graph-RAG retrieval, and products all still see
it. This re-raises finding 2.3 of the previous document with quantified impact.

### 3.6 Success-shaped zeros hid a broken ATT&CK prerequisite — FIXED

Running ATT&CK mapping against the campaign's cyber projects returned
`{"mapped": 0, "skipped": 19}`. That is the same shape as a genuine no-match, so
it read as "the model rejected every candidate". The real cause was that **695
techniques were loaded in Neo4j and the embeddings table was empty** — the RAG
mapping had nothing to match against and could never have matched anything.

`/attack/embed` had the mirror problem: HTTP 200 with `{"embedded": 0}` for four
distinct causes, which reads as "already done". Here it was a trial Cohere key
rate-limiting a 695-technique batch — retryable, and worth saying.

Both now report a reason. This is the same class as §3.1 (a killed collection
reporting `running`) and it cost real investigation time twice in one session:
**an endpoint that returns a plausible-looking zero for a broken precondition is
worse than one that errors.**

### 3.7 `ollama_connected` reports false while Ollama is in active use

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
