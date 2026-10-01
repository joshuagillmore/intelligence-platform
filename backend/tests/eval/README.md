# Extraction eval

Scores entity and relationship extraction (`services/extraction.py`) against
hand-reviewed gold, in all three extraction modes, and records what the real
graph build keeps of the result.

## What is scored

| Set | Path | Documents | Gold entities | Gold relationships |
|---|---|---|---|---|
| `corpus` | `tests/fixtures/extraction_corpus/` | 40 | 93 | 10 |
| `cyber` | `tests/fixtures/extraction_corpus_cyber/` | 3 | 39 | 13 |
| `legacy` (opt-in) | `tests/fixtures/extraction/` | 8 | | |
| `holdout` (opt-in) | `tests/fixtures/extraction_holdout/` | 4 | | |

**`corpus`** is fictional exercise intelligence reporting, built by
`backend/scripts/build_eval_corpus.py` from a local Qdrant: it scrolls the
`kestrel` and `openrep` collections, keeps the chunks with an "Entities
identified in this reporting:" line (233 in `kestrel`, none in `openrep`), and
selects 40 — every one of the 28 distinct entity lines once, then filling by
the least-represented discipline (SIGINT 8, GEOINT 7, HUMINT 7, OSINT 7,
LIAISON 7, assessments 4). **Every classification and releasability marking is
stripped**: banner lines (`NS//REL-NATO`, `CTS//REL-FVEY//REL-NATO`) are
removed whole, portion markings (`(NS)`, `(CTS)`) after each paragraph number
are removed, and the builder refuses to write a file in which a broader
residue pattern still matches. The `EXERCISE — FICTIONAL` banner is kept. A
default-suite test (`test_corpus_fixtures.py`) re-checks every committed file
with an independent pattern.

The entity line was the seed of each gold file, not the answer. Each was
reviewed against its text: places named in the prose were added (Torvik,
Nyhavn, Meran Strait, Ostrand Peninsula, Kirvo airfield); vessels are typed
`Ship` (the hierarchy's type for one) under their bare name, with the hull
number and written form as aliases; units and authorities are
`Organization`; adjectival nationalities ("Valdorian", "Ravenskan"), roles
("Source", "Partner"), unnamed sub-site places ("quay 4") and times are not
entities. A relationship is gold only where a sentence states it: the berth
and arrival sentences (`LOCATED_AT`), "torvald (A-430) of 2nd Naval Auxiliary
Group" (`BELONGS_TO`). Two vessel names (Aldenkirk, Lysgard) appear only in
entity lines; their `Ship` type is a judgement from co-reporting, noted in
those files.

**`cyber`** is the three documents ingested in the 2026-09-30 end-to-end run
that showed the known defects ("Windows" a Location, "Netgear ProSAFE" an
Organization, five of six edges dropped, no edge to CVE-2023-27997). Gold
relationships require the sentence to name, or refer back to, both ends.

## Running it

```bash
cd backend
uv run python tests/eval/run_corpus_eval.py --mode nlp
uv run python tests/eval/run_corpus_eval.py --mode llm --build-neo4j bolt://localhost:7691
uv run python tests/eval/run_corpus_eval.py --mode hybrid --sets corpus cyber legacy holdout
uv run pytest -m eval tests/eval -v        # the same, as tests; excluded by default
```

Each run writes `corpus_eval_<mode>.json` (overall, per set, per type, type
confusion, relationship metrics, per-document detail) and `corpus_eval_<mode>.md`.

- **Billed calls only here.** `llm` and `hybrid` call the model. The script
  loads provider settings from the repo-root `.env` itself (from a worktree,
  the main checkout's), because `tests/conftest.py` blanks every provider
  setting for the unit suite. Keys come from the environment only; the
  database key store is not consulted. The `eval` marker is excluded by
  default (`addopts = -m "not eval"`).
- **Replies are recorded and replayed** (`llm_replies.json`, keyed by model,
  system prompt and message). A fix to what happens after the model answers
  is then measured on identical output; a changed prompt is a new key and is
  asked live. `--refresh-cache` asks live and records over; `--no-cache` asks
  live and records nothing.
- **`--build-neo4j`** runs each document's extraction through
  `graph_builder.build_graph_from_extractions` in a throwaway `eval-…` project
  and reports what the build created, retired, dropped and orphaned. The live
  run's "relationships_dropped 5" was a build number, not an extraction one.
  A build that raises is recorded per document instead of ending the run.
- **Degraded documents are listed**: a document whose model half failed is
  scored as what actually ran (NLP), and the report says so at the top.

Scores: entities match on name or alias (exact first, then Jaro-Winkler and
substring); "typed F1" counts a match only when the type matches too; a
relationship matches when both endpoints match and the type is equal.

## Results (committed, `a5954597`, live Cohere `command-a-plus-05-2026`)

| Mode | Entity P / R / F1 | Typed F1 | Type acc | Rel P / R / F1 | Cyber gold edges | Build: created / dropped |
|---|---|---|---|---|---|---|
| nlp | 0.924 / 0.917 / 0.920 | 0.738 | 0.802 | 0.115 / 0.435 / 0.182 | 8 / 13 | 10 / 0 |
| llm | 0.807 / 0.985 / 0.887 | 0.819 | 0.923 | 0.136 / 0.652 / 0.226 | 11 / 13 | 104 / 4 |
| hybrid | 0.774 / 0.985 / 0.867 | 0.820 | 0.946 | 0.136 / 0.652 / 0.226 | 10 / 13 | 101 / 7 |

No document degraded and no build raised in any of the three. The `llm` run's
replies are the ones recorded in `llm_replies.json`; the `hybrid` run asked
the model separately (`--no-cache`), so its model half is a different sample.

## Before and after, one fix at a time

Every row uses the corrected matcher (below) and, for `llm` and `hybrid`, the
same recorded replies — except step 8, which changed the prompt and so needed
new ones (live; the model is sampled, so step 8 compares two samples, and the
final row is a third). A step marked *unchanged* did not touch that mode.
"Cyber edges" is gold relationships found in the three live-run documents;
"AW share" the fraction of predicted edges that are `ASSOCIATED_WITH`;
"Built / Dropped / Orphan dates" are from the real graph build.

### nlp

| Step | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Cyber edges | AW share | Built | Dropped | Orphan dates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0. baseline `be263d08` | 0.709 | 0.886 | 0.788 | 0.411 | 0.521 | 0.012 | 0.043 | 0.018 | 1/13 | 99% | 1 | 14 | 25 |
| 1. software/hardware typing | 0.714 | 0.909 | 0.800 | 0.453 | 0.567 | 0.011 | 0.043 | 0.018 | 1/13 | 99% | 1 | 14 | 25 |
| 2. threat-actor names | 0.714 | 0.909 | 0.800 | 0.473 | 0.592 | 0.011 | 0.043 | 0.018 | 1/13 | 99% | 1 | 14 | 25 |
| 3. typed edges; none to a date | 0.714 | 0.909 | 0.800 | 0.473 | 0.592 | 0.100 | 0.348 | 0.155 | 8/13 | 90% | 8 | 0 | 25 |
| 4. relationship vocabulary *(unchanged)* | 0.714 | 0.909 | 0.800 | 0.473 | 0.592 | 0.100 | 0.348 | 0.155 | 8/13 | 90% | 8 | 0 | 25 |
| 5. vessels | 0.720 | 0.917 | 0.807 | 0.647 | 0.802 | 0.098 | 0.435 | 0.160 | 8/13 | 90% | 10 | 0 | 25 |
| 6. dates that date something | 0.835 | 0.917 | 0.874 | 0.700 | 0.802 | 0.098 | 0.435 | 0.160 | 8/13 | 90% | 10 | 0 | 2 |
| 7. non-names | 0.924 | 0.917 | 0.920 | 0.738 | 0.802 | 0.115 | 0.435 | 0.182 | 8/13 | 89% | 10 | 0 | 2 |
| 8–9. prompt, place subtypes *(unchanged)* | 0.924 | 0.917 | 0.920 | 0.738 | 0.802 | 0.115 | 0.435 | 0.182 | 8/13 | 89% | 10 | 0 | 2 |
| **final, live** | 0.924 | 0.917 | 0.920 | 0.738 | 0.802 | 0.115 | 0.435 | 0.182 | 8/13 | 89% | 10 | 0 | 2 |

### llm

| Step | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Cyber edges | AW share | Built | Dropped | Orphan dates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0. baseline `be263d08` | 0.339 | 0.985 | 0.504 | 0.434 | 0.862 | 0.039 | 0.565 | 0.073 | 10/13 | 46% | 269 | 19 | 44 |
| 1. software/hardware typing | 0.339 | 0.985 | 0.504 | 0.446 | 0.885 | 0.039 | 0.565 | 0.073 | 10/13 | 46% | 269 | 19 | 44 |
| 2–3. actor names, typed edges *(unchanged)* | 0.339 | 0.985 | 0.504 | 0.446 | 0.885 | 0.039 | 0.565 | 0.073 | 10/13 | 46% | 269 | 19 | 44 |
| 4. relationship vocabulary | 0.339 | 0.985 | 0.504 | 0.446 | 0.885 | 0.044 | 0.565 | 0.082 | 10/13 | 37% | 234 | 16 | 44 |
| 5. vessels | 0.339 | 0.985 | 0.504 | 0.454 | 0.900 | 0.044 | 0.565 | 0.082 | 10/13 | 37% | 234 | 16 | 44 |
| 6. dates that date something | 0.384 | 0.985 | 0.552 | 0.497 | 0.900 | 0.053 | 0.565 | 0.096 | 10/13 | 42% | 234 | 9 | 0 |
| 7. non-names *(unchanged)* | 0.384 | 0.985 | 0.552 | 0.497 | 0.900 | 0.053 | 0.565 | 0.096 | 10/13 | 42% | 234 | 9 | 0 |
| 8. prompt (live replies) | 0.843 | 0.977 | 0.905 | 0.849 | 0.938 | 0.151 | 0.652 | 0.246 | 9/13 | 23% | 92 | 4 | 3 |
| 9. place subtypes | 0.843 | 0.977 | 0.905 | 0.863 | 0.954 | 0.151 | 0.652 | 0.246 | 9/13 | 23% | 92 | 4 | 3 |
| **final, live** | 0.807 | 0.985 | 0.887 | 0.819 | 0.923 | 0.136 | 0.652 | 0.226 | 11/13 | 42% | 104 | 4 | 0 |

### hybrid

| Step | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Cyber edges | AW share | Built | Dropped | Orphan dates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0. baseline `be263d08` | 0.338 | 0.992 | 0.504 | 0.435 | 0.863 | 0.039 | 0.565 | 0.073 | 10/13 | 45% | 270 | 19 | 45 |
| 1. software/hardware typing | 0.338 | 0.992 | 0.504 | 0.446 | 0.885 | 0.039 | 0.565 | 0.073 | 10/13 | 45% | 270 | 19 | 45 |
| 2–3. actor names, typed edges | 0.338 | 0.992 | 0.504 | 0.446 | 0.885 | 0.039 | 0.565 | 0.073 | 10/13 | 45% | 270 | 19 | 45 |
| 4. relationship vocabulary | 0.338 | 0.992 | 0.504 | 0.446 | 0.885 | 0.044 | 0.565 | 0.082 | 10/13 | 37% | 235 | 16 | 45 |
| 5. vessels | 0.339 | 0.992 | 0.506 | 0.456 | 0.901 | 0.044 | 0.565 | 0.082 | 10/13 | 37% | 235 | 16 | 45 |
| 6. dates that date something | 0.382 | 0.985 | 0.551 | 0.496 | 0.900 | 0.052 | 0.565 | 0.096 | 10/13 | 42% | 235 | 9 | 0 |
| 7. non-names | 0.382 | 0.985 | 0.551 | 0.496 | 0.900 | 0.052 | 0.565 | 0.096 | 10/13 | 42% | 235 | 9 | 0 |
| 8. prompt (live replies) | 0.838 | 0.977 | 0.902 | 0.846 | 0.938 | 0.151 | 0.652 | 0.246 | 9/13 | 23% | 92 | 4 | 3 |
| 9. place subtypes | 0.838 | 0.977 | 0.902 | 0.860 | 0.954 | 0.151 | 0.652 | 0.246 | 9/13 | 23% | 92 | 4 | 3 |
| **final, live** | 0.774 | 0.985 | 0.867 | 0.820 | 0.946 | 0.136 | 0.652 | 0.226 | 10/13 | 23% | 101 | 7 | 1 |

Hybrid's NLP half did gain typed edges at step 3, but the model already had
each of them, so the merged set did not change.

### The fixes

1. **Software and hardware** — a name modifying a device noun ("A Netgear
   ProSAFE router") is `Hardware`, a tool noun ("built-in Windows tools")
   `Software`; a vendor alone is an `Organization`; living-off-the-land
   binaries (netsh, ntdsutil, wmic, …) are extracted as `Software` and
   re-typed so when the model calls them TTPs. *Known defects 1 and 2.*
2. **Threat-actor names** — Microsoft weather families (Volt Typhoon),
   Storm-NNNN, UNC/FIN clusters; "Super/Tropical Typhoon" and the Eurofighter
   excluded.
3. **Typed edges the sentence states; no generic edge to a date** — the
   participle subject ("actor attributed to China"), "the group"/"the actor"
   resolved to the last-named threat actor, appositive before modifier ("the
   Fortinet vulnerability CVE-2023-27997" names the CVE), conjuncts and lists,
   relation-bearing prepositions, USES + Vulnerability = EXPLOITS, and no
   co-occurrence edge to a Date (graph nodes are never Dates; those five edges
   were the live run's drops). Verb map: rely → USES, abuse → USES (a
   vulnerability object is still EXPLOITS), arrive/berth/dock/moor →
   LOCATED_AT. *Known defects 3 and 4.*
4. **Relationship vocabulary** — model synonyms keep their type (BERTHS_AT →
   LOCATED_AT, TARGETED → TARGETS, MEMBER_OF → BELONGS_TO); a type with no
   meaning in the vocabulary ("REPORTED", "DOES_NOT_ESTABLISH") is no longer
   stored as `ASSOCIATED_WITH` but dropped and counted in the log.
5. **Vessels** — "Name (A-411)" and "bulk carrier Mirenda" / "patrol vessels
   Brenna and Sarn" make a `Ship` in every mode; "Ship (hull) of Unit" is
   BELONGS_TO; hybrid merges the hull-number entity with the model's by alias
   and re-points NLP edges at the entity they merged into.
6. **Dates** — a Date must carry a month, weekday, year or quarter ("6
   months", "1742Z" and "the period" do not, and only ever became orphans);
   "24 May 2023" is one date, not also "May 2023".
7. **Non-names** — adjectival nationalities ("Valdorian naval liaison"),
   lower-case misfires under name labels ("liaison", "quay 4") and signal or
   navigation acronyms (AIS, GNSS, VHF).
8. **Prompt** — the `entity_extraction` skill asked the model to "err on the
   side of inclusion"; it now says what an entity is and is not, types
   vessels, tools and products, and says unlisted relationship types are
   discarded. Its examples are deliberately not from this corpus (a test
   checks), or the eval would be scoring the prompt.
9. **Place subtypes** — "Airfield", "Harbour", "Naval Base", … map to
   `Location` instead of landing as Custom.

Not a metric row: a model-returned indicator is stored refanged
("evil-c2[.]com" → "evil-c2.com"). Two live runs died in the graph build on
the bracket (`urlsplit` raises "Invalid IPv6 URL" in
`graph_builder._host_of`); the replies were lost with the runs, so the fix is
pinned by a unit test of that reply shape.

### Regression check on the older sets (NLP)

| Step | legacy F1 (P / R) | legacy typed F1 | holdout F1 (P / R) | holdout typed F1 | rel F1 legacy / holdout |
|---|---|---|---|---|---|
| 0. baseline | 0.532 (0.376 / 0.907) | 0.442 | 0.710 (0.594 / 0.882) | 0.497 | 0.004 / 0.000 |
| 3. typed edges | 0.531 (0.376 / 0.907) | 0.441 | 0.710 (0.594 / 0.882) | 0.497 | 0.014 / 0.013 |
| 5. vessels | 0.533 (0.378 / 0.907) | 0.443 | 0.723 (0.612 / 0.882) | 0.506 | 0.014 / 0.013 |
| 6. dates | 0.535 (0.382 / 0.897) | 0.450 | 0.732 (0.625 / 0.882) | 0.512 | 0.013 / 0.013 |
| 7. non-names | 0.538 (0.385 / 0.890) | 0.453 | 0.736 (0.632 / 0.882) | 0.515 | 0.014 / 0.013 |

The legacy recall that went (0.907 → 0.890) was credit the matcher gave junk:
a date "2270, 2321" matching "UNSCR 2270", "Australian" matching "Australian
Defence Force", "Georgian" matching "Georgia".

## The matcher bug this found

`extraction_eval._entity_matches` took the shorter and longer name with
`min()` and `max()`, which return the same argument when the lengths tie, so
the substring rule found a name inside itself: "Quay 4" matched "Torvik",
"Sarn" matched "Mira". Every eval built on it counted such pairs. Fixed
(`8e850822`); with it, the baseline LLM relationship recall is 0.565, not the
0.783 the first committed run reported, and every number above uses the fixed
matcher.

## Known remaining errors

- NLP types fictional places it does not know as Organizations ("Torvik" 7
  times, "Nyhavn" 3). A locative-preposition rule would fix these and
  mistype "engineers at Airbus"; not done.
- Vessels named only in an entity line, with no vessel noun or hull number
  ("Mirenda, Stellar Vane"), stay Person/Organization in NLP.
- The model still extracts the `EXERCISE — FICTIONAL` banner as a Document in
  some replies, and some reporting phrases as Events.
- NLP relationship precision stays low (0.115): co-occurrence edges are 89% of
  its output. The graph build discards them anyway (`ASSOCIATED_WITH` below
  `cooccurrence_confidence_min` = 0.55), without counting them.
