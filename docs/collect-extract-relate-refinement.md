# Collect → Extract → Relate refinement loop

A bounded Loopy refinement loop (scaffolds: Loop Library #023 self-improving
champion + #016 ticket-to-PR-ready). Each cycle fixes the single highest-value
defect across the three tracks, verifies against the frozen eval corpus +
rubric, keeps only regression-free wins, and stops when every track's exit gate
passes or a track shows no progress for two cycles.

## Baseline (2026-07-19, `main` @ 4f277a35, 8-fixture eval corpus)

- **Entity extraction:** Precision **0.457**, Recall **0.942**, F1 **0.598** — over-extraction (727 predicted / 300 gold). Recall gaps: acronym orgs (SVR/NCSC/CISA/GRU), some persons, vessels, crypto wallets, equipment types. ~2s / 8 docs.
- **Relationships:** F1 **0.011**. 1255 predicted, **99.7% blanket `ASSOCIATED_WITH`**, 2 typed edges. Corpus has almost no relationship gold.
- **Show Evidence:** fake — `documents.py:94-130` takes one entity name, substring-searches doc text; frontend reconstructs co-occurrence client-side. No per-edge provenance. LLM produces an evidence sentence (`extraction.py:725`) but it was dropped at `graph_builder.py:196`.
- **PIR→plan→crawl:** the live agentic pipeline never searches — RESOLVE (`agentic.py:36-58`) hallucinates URLs from LLM recall; ddgs is wired only to the legacy runner. EEIs discarded; no relevance gate; open feedback loop (defaults to `satisfied:true`).

## Exit gates

| Track | Gate |
|---|---|
| A · Entity extraction | Precision **≥0.75** (from 0.46), Recall held **≥0.90**, on a holdout split; recover the specific blind-spots |
| B · Relationships + Show Evidence | Every edge carries a persisted evidence sentence; Show Evidence returns that for the specific edge (verified on sampled pairs); blanket `ASSOCIATED_WITH` share drops from 99.7% with each retained edge defensible; space-hungry UI trimmed |
| C · PIR→plan→crawl | Resolution grounded in real search; per-source queries + EEIs carried through; relevance gate before ingest; feedback loop closed; SSRF guard preserved |

Confirmed with the user (2026-07-19): relationships → **prune hard, keep evidence-backed**; crawl track → **small live runs authorized**; sequence → **extraction + relationships together**, then crawl. Every change reviewer-gated; extraction track holdout-validated to avoid overfitting the 8 fixtures.

## Cycle log

### Cycle 1 — persist the relationship evidence sentence end-to-end ✅
**Action:** Added `evidence: str` to the `Relationship` model; NLP `_add_rel` now captures the source sentence; new `_clean_evidence()` tightens it to the in-context span around both entity names (collapses whitespace, windows ±45 chars, ASCII `...` clip) since spaCy glues doc headers onto the first sentence; `graph_builder` stops dropping evidence; `store.get_relationships` now also returns `source_name`. LLM path already carried `evidence` — now cleaned the same way.
**Verify:** Full suite **443 passed**; eval relationship count unchanged at **1255** (purely additive); 100% of edges now carry clean evidence, e.g. `[ASSOCIATED_WITH] Cozy Bear -> the Russian Foreign Intelligence Service` → *"APT-29, also known as Cozy Bear and attributed to the Russian Foreign Intelligence Service (SVR), has launched a new phishing campaign targeting European government agencies."* ruff clean.
**Outcome:** Foundation for Track B in place — edges now have real per-edge provenance to surface.

### Cycle 2b — clean entity-precision fixes (determiners, boilerplate, demonyms) ✅
**Action:** In `_postprocess_entities`: strip leading determiners ("the Russian Foreign Intelligence Service" → "Russian Foreign Intelligence Service"); drop intelligence-report boilerplate (`REPORT_BOILERPLATE`: "Handling Caveat", "Source Reliability", etc. — title-cased, so the all-caps filter missed them); drop bare nationality demonyms (`DEMONYMS`: "European", "the French", etc. — spaCy tags NORP→Organization). Principled intel-domain normalizations, not fixture-specific.
**Verify (train, 8 fixtures):** Entity **P 0.457→0.494, R 0.942→0.956** (recall *up* — determiner-stripping improved gold matching), F1 0.598→0.629; false positives **531→419**. ruff clean, full suite unaffected.
**Outcome:** Regression-free precision gain. Remaining FP: Dates (~123, orphan-date pruning next), tool/malware/threat-actor mis-typing (~typing rules), generic Locations (~87, relevance-based, deferred). Overfitting guard: a 4-doc holdout corpus is being built to validate these before promotion.

