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
**Outcome:** Regression-free precision gain. Remaining FP: Dates (~123, orphan-date pruning next), generic Locations (~87, relevance-based, deferred).

### Cycle 2d — domain typing + military-designation recovery ✅
**Action:** Threat-actor patterns (`APT-NN`, CrowdStrike `<Adj> <Animal>` handles → ThreatActor), `Type NNN` military designations → EquipmentType (extracted via regex in `_extract_cyber_entities` since spaCy misses them entirely — these were false negatives), and a known-malware set → Malware. Fixed a regression Cycle 2b had exposed: `test_type_accuracy[military_osint_1]` dipped to 0.29 because improved recall matched more ambiguous ship-names; recovering the `Type 075/071` designations with the correct type cleared it back over 0.30 (proper fix, not a threshold change).
**Verify:** `military_osint_1` type-accuracy test passes; all 20 extraction-quality tests pass; train P=0.493 R=**0.962** F1=0.629. Full suite **443 passed**, ruff clean.

### Cycle 3 — relationship prune-hard: drop cross-sentence Stage C ✅
**Action:** Removed the Stage-C cross-sentence `ASSOCIATED_WITH` bridge (discourse-marker, confidence 0.4) — it links entities *across* sentences, so it can't carry the single-sentence evidence the "prune hard, keep evidence-backed" directive requires. Dropped its now-dead plumbing (`prev_sent_entities`, `discourse_markers`).
**Verify:** Eval relationship count **1255 → 1062**; entity metrics unchanged; full suite 443 passed.

### Holdout corpus (overfitting guard) ✅
4 independently-labeled intel reports in `tests/fixtures/extraction_holdout/` + `run_holdout_eval.py` (reuses the eval metric fns). Current NLP-mode holdout: **Entity P=0.614 R=0.912 F1=0.734**, Rel F1=**0.000** (only `ASSOCIATED_WITH` emitted — gold wants typed relations; confirms Track B must add typed-relation extraction, not just prune). The higher holdout precision vs train (0.61 vs 0.49) shows the Cycle-2 fixes generalize.

### Cycle 4 — LLM/hybrid extraction for typed relations ✅
**Why:** NLP-only can't produce typed relations (Rel F1 = 0); an LLM (Ollama qwen2.5:14b, local, no rate limit) emits `USES/TARGETS/ATTRIBUTED_TO/EXPLOITS/...` *with* evidence.
**Action:** Normalize LLM output — fine-grained types (IntelligenceService, Backdoor) mapped to canonical (`_normalize_llm_entity_type`), rel_types validated against the allowlist (`_normalize_rel_type`). Rebuilt the hybrid merge to be **LLM-primary**: LLM entities + only the deterministic NLP **regex** IOCs it missed (not spaCy over-extraction); LLM typed+evidence relations + NLP typed relations, **dropping blanket NLP `ASSOCIATED_WITH`** (co-occurrence noise).
**Verify (hybrid vs NLP baseline):**
| | Entity P | Entity R | Entity F1 | Rel F1 | ents | rels |
|---|---|---|---|---|---|---|
| Train NLP | 0.493 | 0.962 | 0.629 | 0.011 | 727 | 1255 |
| **Train hybrid** | **0.713** | 0.733 | **0.708** | **0.170** | 321 | 209 |
| Holdout NLP | 0.614 | 0.912 | 0.734 | 0.000 | — | — |
| **Holdout hybrid** | **0.875** | 0.800 | **0.830** | **0.301** | 62 | 40 |

Precision + relationship F1 + leanness all jump dramatically; recall trades down (LLM is selective) — recall-recovery is the next tune. Full suite still 443 (NLP path untouched; LLM/hybrid falls back to NLP without a provider).

### Cycle 5 — Show Evidence surfaces real per-edge evidence + UI trim ✅ (`f6b8ab13`)
**Action:** Frontend now renders each edge's persisted `evidence` sentence directly (network list + selected-edge panel; cyber/geo lists) with a "re-run extraction" fallback — deleted the ~70-line client-side document-substring reconstruction. Compacted relationship rows (confidence chip vs full-width bar); Edge Overview hides noise-tier ASSOCIATED_WITH behind a default-collapsed disclosure. lint + build clean.

### Cycle 6 — Track C: ground agentic resolution in real search ✅ (`04f7c87c`)
**Action:** The RESOLVE phase asked the LLM to "generate real URLs" (hallucination). Now `resolve_sources` runs live DuckDuckGo search (PIR + source), the LLM SELECTS from real results, and a hard allow-list filter guarantees no invented URLs; falls back to generation only when search is empty. SSRF guard preserved. 4 mocked tests pass. Live `web_search` verified returning on-topic URLs.

**Next:** finalize hybrid mode (measure refined merge; set as default if it wins) → re-extract for live Show Evidence → remaining Track C (relevance gate, close feedback loop) → reviewer-gate + merge.

