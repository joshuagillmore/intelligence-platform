# PIR loop test — findings

**Date:** 2026-07-26 · **Method:** autonomous end-to-end runs of real Priority
Intelligence Requirements — PIR → refinement → collection plan → live crawl →
extraction → graph → analytic techniques → written products — across cyber,
maritime and multi-source-corroboration scenarios.

Two root-cause bugs were found and fixed during the run. The rest is recorded
here rather than half-implemented.

---

## 1. Fixed during the loop

### 1.1 The collection planner was never receiving the PIR

**Severity: high.** Two symptoms that looked unrelated turned out to be one bug.

The refinement prompt asks for "the refined PIR on the first line", but models
label their output (`Refined PIR:`, `**Refined PIR:**`). The parser took line 0
verbatim, so `refined_pir` became the literal label — 12 characters — and the
real requirement was pushed into the plan description.

That string was then interpolated into the source-generation prompt, so the
planner received a bare label. A maritime PIR about attacks on Red Sea shipping
produced NVD vulnerability feeds, VirusTotal malware and Dark Web forums. It
looked like cyber over-fitting; the planner had simply never been told the
subject.

| | before | after |
|---|---|---|
| `refined_pir` | 12 chars (`"Refined PIR:"`) | 202 chars of requirement |
| generated sources | NVD, VirusTotal, Dark Web | Maritime Security Center, IMB piracy reports, MarineTraffic |

Fixed in `_split_refinement` (9 unit tests). The plan prompt now also carries the
original PIR for domain context.

### 1.2 Corroboration was never populated

**Severity: high.** `Relationship` has carried `corroboration_count`,
`corroboration_sources` and `corroboration_agreement` from the start. Nothing
ever wrote them, because `create_relationship` called
`apoc.create.relationship` unconditionally — always CREATE, never MERGE.

Measured with three documents about one incident, two independently asserting
*"Ansar Allah TARGETS MV Northern Star"*:

| | before | after |
|---|---|---|
| edges created | 4 duplicates | 1 |
| `corroboration_count` | 1 | 2 |
| `corroboration_sources` | `[]` | 2 documents |

Only a *different* source document counts — two mentions inside one document are
one source. This is what makes the evidence chain's Corroboration field real; it
could only ever read "Single source" before.

---

## 2. Found, not fixed — recommended work

### 2.1 Contradiction is not detected — FIXED after this was written

A document explicitly denying a claim — *"Ansar Allah did not conduct the attack
on MV Northern Star"* — produces no `CONFLICT`. It is either dropped or becomes
another agreeing edge. `corroboration_agreement` never leaves its `AGREE`
default.

This matters more than corroboration: an intelligence system that cannot
represent *disputed* reporting will quietly present contested claims as settled.
The field and the UI state already exist (the evidence chain renders CONFLICT in
red) — only the detection is missing.

**Implemented** (commit `a3d26b83`). Four parts were needed; changing only the
prompt did nothing, because `extraction.py` was dropping the field:

1. `entity_extraction` asks for a per-relationship `polarity`.
2. `extraction.py` maps it through.
3. `Relationship.polarity` carries it; `graph_builder` normalises it.
4. `create_relationship` treats an assert/deny collision as CONFLICT, takes the
   *weaker* confidence, and keeps a dispute sticky.

Measured: Reuters asserting the attack and Janes denying it moved from
`AGREE, corroboration 2, confidence 0.95` — a denial *raising* confidence — to
`CONFLICT, corroboration 2, confidence 0.85`.

Still open: NLP-mode extraction has no negation handling, so denials are only
detected on the LLM path.

### 2.2 Domain types exist but are rarely selected

Maritime entities landed as `Custom`, `Organization` or `Technology`:

- `MV Aurora Trader`, `Stellar Horizon` (vessels) → `Custom`
- `AIS` (a navigation system) → `Organization`, and then appeared in an ACH
  hypothesis as a candidate *attacker*
- `Ghadr-380` → `Weapon` (correct — the type exists but is rarely selected)

**Correction to the first draft of this document:** the taxonomy is not missing.
`entity_extraction.yaml` already offers `Ship`, `Aircraft`, `Missile`,
`Submarine`, `Drone`, `Radar` under Equipment. The problem is *selection* — the
model reaches for `Custom` or `Organization` instead.

**Proposal:** few-shot examples in the extraction prompt for non-cyber domains,
and a validation pass that re-types obvious cases (a name prefixed "MV"/"USS" is
a Ship). Cheaper than extending the hierarchy, and addresses the real cause.

### 2.3 Extraction noise on crawled pages

Live-crawled pages produced entities like `+1-813` (a phone number typed as
`Organization`), `Advisory`, `About`, and navigation furniture. This is the same
class of noise that made the 500-node graph illegible earlier.

**Proposal:** an **entity-resolution / hygiene agent** — the seventh agent in the
earlier roster. Post-extraction pass that drops obvious furniture, merges
near-duplicates, and flags mis-typed entities for review. The gap-analysis agent
already reports isolated entities; this would act on them.

### 2.4 No corroboration or conflict surfaced in the UI yet

Now that corroboration accumulates, the evidence chain will show "2 sources" —
but nothing in the graph view distinguishes a well-corroborated edge from a
single-sourced one. **Proposal:** edge thickness or a corroboration badge in the
graph, and a filter for "single-sourced claims only" as a triage tool.

### 2.5 Source reliability is not auto-populated

Almost every relationship reads `Ungraded`. The `source_evaluation` agent exists
and produces admiralty grades, but nothing runs it automatically on ingest.
**Proposal:** run it as a post-ingest hook (opt-in, like auto-enrich), so
documents arrive graded and the evidence chain shows a grade rather than a
caveat.

### 2.6 Missing data sources for non-cyber work

The connector set is cyber-shaped: web scrape, RSS, API feed, file upload,
database. A maritime PIR wanted, and could not have:

- **AIS / vessel tracking** (MarineTraffic, AISHub) — the planner asked for it and
  the connector does not exist
- **UKMTO / IMB incident feeds** — structured maritime incident reporting
- **ACLED / GDELT** — event datasets for political and conflict reporting
- **Sanctions and corporate registries** — OFAC, OpenCorporates

**Proposal:** a small connector SDK plus 2–3 reference non-cyber connectors. The
generic `api_feed` connector cannot authenticate or paginate, so those sources
fail at execution even when the planner correctly identifies them.

### 2.7 Document typing on ingest

Everything ingests as a generic `Document` named `text_input`. There is no way to
say "this is an INTREP / SITREP / press report / HUMINT summary", which is what
drives reliability weighting in real tradecraft.
**Proposal:** a `document_type` on ingest, defaulted by connector, surfaced in the
evidence chain next to the reliability grade.

### 2.8 Collection throughput

A 5-source plan with `max_results_per_source=2` ran for over 40 minutes and
completed 1 source. Per-document LLM summarisation plus hybrid extraction on a
contended local model dominates. **Proposal:** make per-document summarisation
opt-in, batch extraction calls, and surface an ETA. The status endpoint now
reports real progress, which makes the slowness visible but not shorter.

### 2.9 Minor

- `source_evaluation` returns `entity_count: 0` for documents that demonstrably
  produced entities — the per-document yield metric looks miswired.
- Products cap evidence at 40 relationships (`_MAX_EVIDENCE`); both test products
  hit the cap, so the appendix is truncated without saying so.

---

## 3. What worked well

- **PIR refinement** — genuinely good analytic output: adds time bounds, EEIs and
  measurability to a vague requirement.
- **ACH** — on the maritime data it produced four competing hypotheses and rated
  *"multiple actors collaborated: Houthi targeting, Iranian missile, third-party
  launch"* above the obvious single-actor explanation. That is real reasoning
  about an Iranian weapon with a Houthi claim.
- **Gap analysis** — grounded and specific, naming the actual isolated entities.
- **Semantic search** — complementary to keyword in practice: *"anti-ship missile"*
  returned nothing by keyword (the text says "anti-ship *ballistic* missile") and
  the right passage by meaning.
- **Extraction on non-cyber prose** — 17 entities / 12 relationships from a
  maritime incident report, correctly typed apart from vessels.
- **Geo enrichment across domains** — correctly geocoded *Bab-el-Mandeb strait*.
- **Provenance end-to-end** — `source_doc_id` now flows from extraction through
  the graph to the product's evidence appendix.

---

## 4. Suggested priority

1. **Contradiction detection** (2.1) — the largest capability gap, and the field
   and UI already exist.
2. **Entity taxonomy + hygiene agent** (2.2, 2.3) — the graph is currently too
   noisy to answer the PIR it was built from.
3. **Auto source grading** (2.5) — turns "Ungraded" from a caveat into a feature.
4. **Non-cyber connectors** (2.6) — otherwise "all-source" is aspirational.
5. Corroboration in the graph view (2.4), document typing (2.7), throughput (2.8).
