# Extraction eval

Scores entity and relationship extraction (`services/extraction.py`) against
hand-reviewed gold, in all three extraction modes, and records what the real
graph build keeps of the result.

## What is scored

| Set | Path | Documents | Gold entities | Gold relationships |
|---|---|---|---|---|
| `openrep` (primary) | `tests/fixtures/extraction_corpus_openrep/` | 40 | 510 | 73 |
| `kestrel` | `tests/fixtures/extraction_corpus/` | 40 | 93 | 10 |
| `cyber` | `tests/fixtures/extraction_corpus_cyber/` | 3 | 39 | 13 |
| `legacy` (opt-in) | `tests/fixtures/extraction/` | 8 | | |
| `holdout` (opt-in) | `tests/fixtures/extraction_holdout/` | 4 | | |

The first three run by default. Every report opens with a row per set and a
**combined** row, and lists misses, extras and mistypes per set.

**`openrep`** is the primary set: 40 chunks of the local Qdrant collection
`openrep-deep` (31,723 points), one per distinct `doc_id`, built by
`backend/scripts/build_eval_corpus.py --corpus openrep-deep`.

- **What it is.** 13 synthetic analyst products (each distinct question
  once), 2 synthetic "contradiction" documents, and 25 chunks of public-domain
  Congressional Research Service text that the collection carries under
  fictional metadata. The CRS chunks are chosen by subject, read from the
  text because the collection's topic labels are loose: Iran maritime 5,
  Russian hybrid warfare 5, counter-UAS 4, naval 4, Indo-Pacific 4,
  missile/space 3. Only body text of 800–3,600 characters is taken; footnotes,
  citation lists and URL-bearing chunks are not.
- **Canary material is excluded.** The collection plants canary documents.
  The builder skips every document flagged as one, every chunk carrying one
  of their tokens or citing one, and every chunk containing the word. It
  also skips the kestrel Torvik material, which is already the `kestrel`
  set.
- **Every classification and releasability marking is stripped**, as for
  `kestrel` (below), and the builder refuses to write a file in which a
  residue pattern still matches. Each file opens with a notice saying what
  it is (a synthetic product, CRS text under fictional metadata, or a
  fabricated document) and that its markings have been removed. A
  default-suite test re-checks every committed file for markings, canary
  material and the notice.
- **Gold is hand-labelled by reading each chunk.** There is no seed line:
  510 entities (Location 152, Organization 132, Date 123, Person 34,
  Document 33, Event 12, Weapon 10, Ship 10, Technology 3, Drone 1) and 73
  relationships (BELONGS_TO 35, TARGETS 18, DEPLOYED_AT 6, SUPPLIED_BY 5,
  COMMANDED_BY 3, LOCATED_AT 3, USES 2, FUNDED_BY 1). The conventions:
  - **Strict.** An entity is something an analyst would want as a graph
    node: named people, organizations, places and systems or platforms; the
    documents that matter to the text (executive orders, acts, NDAAs, named
    strategies); named operations and exercises; and calendar dates that
    date an action.
  - **Not entities.** Nationality adjectives, roles, administrations ("the
    Trump Administration"; the person is the node), unnamed events, fiscal-year
    labels, durations and citations (report numbers, U.S.C. references).
  - **One node per thing.** A country and its government are one entity
    ("PRC", "China", "People's Republic of China"), and a capital standing for
    its government ("Tehran", "Moscow") is an alias of it. An acronym is an
    alias of the name it abbreviates, and an executive order carries each way
    it is written.
  - **Canonical types.** Location covers countries, regions, seas, cities
    and bases. Organization covers government bodies, militaries, units,
    companies and groups. The others are Person; Weapon for missile and
    air-defence systems; Ship, Submarine, Aircraft or Drone for a platform;
    Technology for defence programmes and systems; Document, Event and Date.
  - **Relationships only where a sentence states them**, read the way the
    vocabulary names them: "Iran transferred missiles to Russia" is Russia
    SUPPLIED_BY Iran.

**`kestrel`** (called `corpus` before the openrep phase) is fictional
exercise intelligence reporting, built by
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
uv run python tests/eval/run_corpus_eval.py --mode hybrid --sets openrep kestrel cyber legacy holdout
uv run python tests/eval/run_corpus_eval.py --mode hybrid --replay-only   # recorded replies only, never billed
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

**Relationships are scored twice, `typed` and `all`.** `all` scores every
predicted edge, as every run before 2026-10-01 did. `typed` leaves out two
kinds of edge, on the prediction and the gold side alike:

- **generic associations** (`ASSOCIATED_WITH`): an assertion that two things
  are related without saying how, which the gold conventions do not label;
- **date links**: `OCCURRED_ON`, or any edge with a `Date` endpoint. These are
  legitimate: they are how an event gets its `event_datetime`, which is what
  the timeline sorts by, and the graph build absorbs the date into the event
  and retires the edge. The gold does not label them either.

Against a gold that labels neither, both kinds counted only as false
positives: of the model's 722 openrep edges, 230 were generic and 123 date
links, so relationship precision said more about how often the model dates an
event than about whether its typed relations are right. `typed` answers that
question; `all` stays so the noise is still visible. The gold files are
unchanged (none of the 96 gold edges is of either kind), and recall is the
same in both figures. Each report also counts predicted edges by class
(typed / generic / date link) and lists the edges the extraction itself
dropped, by reason. `--replay-only` refuses to ask the model: a request with
no recorded reply degrades its document, which the report lists, instead of
being billed.

## Results (committed)

`corpus_eval_{nlp,llm,hybrid}.{json,md}`, run at `26704091` with
`--build-neo4j` (llm and hybrid with `--replay-only`, replaying the live run
recorded at `0fad4a12`). Relationship figures are `typed` and `all` (see
above); "Gold edges" is typed TP / gold.

| Mode | Set | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel typed P / R / F1 | Rel all P / R / F1 | Gold edges |
|---|---|---|---|---|---|---|---|---|---|
| nlp | openrep | 0.674 | 0.949 | 0.788 | 0.728 | 0.924 | 0.649 / 0.507 / 0.569 | 0.060 / 0.507 / 0.107 | 37/73 |
| nlp | kestrel | 0.896 | 0.925 | 0.910 | 0.656 | 0.721 | 1.000 / 0.200 / 0.333 | 0.040 / 0.200 / 0.067 | 2/10 |
| nlp | cyber | 1.000 | 0.923 | 0.960 | 0.960 | 1.000 | 1.000 / 0.615 / 0.762 | 0.210 / 0.615 / 0.314 | 8/13 |
| nlp | **combined** | 0.713 | 0.944 | 0.812 | 0.731 | 0.899 | 0.702 / 0.490 / 0.577 | 0.067 / 0.490 / 0.117 | 47/96 |
| llm | openrep | 0.632 | 0.949 | 0.759 | 0.707 | 0.932 | 0.091 / 0.397 / 0.149 | 0.044 / 0.397 / 0.080 | 29/73 |
| llm | kestrel | 0.802 | 1.000 | 0.890 | 0.823 | 0.925 | 0.316 / 0.600 / 0.414 | 0.143 / 0.600 / 0.231 | 6/10 |
| llm | cyber | 0.974 | 0.949 | 0.961 | 0.961 | 1.000 | 0.458 / 0.846 / 0.595 | 0.393 / 0.846 / 0.537 | 11/13 |
| llm | **combined** | 0.667 | 0.956 | 0.786 | 0.735 | 0.935 | 0.128 / 0.479 / 0.202 | 0.064 / 0.479 / 0.113 | 46/96 |
| hybrid | openrep | 0.602 | 0.971 | 0.743 | 0.700 | 0.941 | 0.145 / 0.726 / 0.241 | 0.076 / 0.726 / 0.138 | 53/73 |
| hybrid | kestrel | 0.795 | 1.000 | 0.886 | 0.819 | 0.925 | 0.316 / 0.600 / 0.414 | 0.143 / 0.600 / 0.231 | 6/10 |
| hybrid | cyber | 0.974 | 0.949 | 0.961 | 0.961 | 1.000 | 0.458 / 0.846 / 0.595 | 0.393 / 0.846 / 0.537 | 11/13 |
| hybrid | **combined** | 0.640 | 0.974 | 0.772 | 0.728 | 0.942 | 0.171 / 0.729 / 0.277 | 0.091 / 0.729 / 0.162 | 70/96 |

- **One live run, then replay.** The `entity_extraction` prompt changed at
  `0fad4a12`, so the recorded replies no longer applied. `llm` asked Cohere
  `command-a-plus-05-2026` once for all 83 documents (`--concurrency 2
  --retries 3`): 83 calls, no 429, no retry, no degraded document. Every
  later run replays those replies; `hybrid` replays them too, so its model
  half is the same sample as `llm`'s. The old-prompt replies stay in
  `llm_replies.json` for the commits that replay them.
- No document degraded and no graph build raised.
- **Trial-key limits.** The repo-root key is a Cohere trial key: 20 calls a
  minute and 1,000 a month. Replaying is what makes a fix-by-fix record
  affordable on it; `--replay-only` makes sure a measuring run cannot spend
  any of it.
- The previous phase's committed results (at `719b9ca6`) are the step 0–1
  row of each table below.

## Extraction precision (2026-10-01): one task at a time

Plan: `docs/design/plans/2026-10-01-extraction-precision-and-response-models.md`,
package WP-E. Each row is that commit's code on the three sets. Steps 0–3a
replay the old-prompt replies (the previous phase's); step 3b changed the
prompt and is the one live run; steps 4 and 5 replay the live run's replies,
so step 3b to 5 compare identical model output, while 3a to 3b compares two
samples as well as two prompts. *(unchanged)* means the step did not touch
that mode. "Typed / generic / date" counts predicted edges by class;
"Dropped" is model edges the extraction dropped for an unlisted endpoint, then
edges the graph build dropped for an unknown endpoint (the
`below_cooccurrence_min` drops, all of NLP's generic edges, are not in it);
"Built" is edges the graph build wrote.

#### nlp

| Step | Ent F1 | Typed F1 | Rel typed P / R / F1 | Rel all P / R / F1 | Gold edges | Typed / generic / date | Dropped: unlisted / build unknown | Built | openrep typed F1 / all F1 |
|---|---|---|---|---|---|---|---|---|---|
| 0–1. baseline `c8aacd2a`, scored typed and all | 0.799 | 0.716 | 0.691 / 0.490 / 0.573 | 0.062 / 0.490 / 0.110 | 47/96 | 68 / 691 / 3 | 0 / 11 | 67 | 0.565 / 0.099 |
| 2. generic associations | 0.799 | 0.716 | 0.691 / 0.490 / 0.573 | 0.065 / 0.490 / 0.115 | 47/96 | 68 / 648 / 3 | 0 / 4 | 67 | 0.565 / 0.105 |
| 3a–3b. listed endpoints, prompt *(unchanged)* | 0.799 | 0.716 | 0.691 / 0.490 / 0.573 | 0.065 / 0.490 / 0.115 | 47/96 | 68 / 648 / 3 | 0 / 4 | 67 | 0.565 / 0.105 |
| 4. government ↔ country | 0.806 | 0.722 | 0.691 / 0.490 / 0.573 | 0.066 / 0.490 / 0.116 | 47/96 | 68 / 641 / 3 | 0 / 4 | 67 | 0.565 / 0.106 |
| 5. acronyms, headings | 0.812 | 0.731 | 0.702 / 0.490 / 0.577 | 0.067 / 0.490 / 0.117 | 47/96 | 67 / 635 / 3 | 0 / 0 | 67 | 0.569 / 0.107 |

#### llm

| Step | Ent F1 | Typed F1 | Rel typed P / R / F1 | Rel all P / R / F1 | Gold edges | Typed / generic / date | Dropped: unlisted / build unknown | Built | openrep typed F1 / all F1 |
|---|---|---|---|---|---|---|---|---|---|
| 0–1. baseline `c8aacd2a`, scored typed and all | 0.767 | 0.708 | 0.102 / 0.458 / 0.167 | 0.053 / 0.458 / 0.095 | 44/96 | 430 / 276 / 126 | 0 / 75 | 649 | 0.131 / 0.073 |
| 2. generic associations | 0.767 | 0.708 | 0.102 / 0.458 / 0.167 | 0.053 / 0.458 / 0.095 | 44/96 | 430 / 271 / 126 | 0 / 75 | 644 | 0.131 / 0.073 |
| 3a. listed endpoints (parser) | 0.767 | 0.708 | 0.104 / 0.438 / 0.168 | 0.056 / 0.438 / 0.099 | 42/96 | 403 / 234 / 120 | 68 / 4 | 645 | 0.130 / 0.075 |
| 3b. prompt rules (live replies) | 0.782 | 0.707 | 0.127 / 0.479 / 0.201 | 0.063 / 0.479 / 0.112 | 46/96 | 362 / 232 / 131 | 66 / 3 | 592 | 0.148 / 0.080 |
| 4. government ↔ country | 0.786 | 0.735 | 0.128 / 0.479 / 0.202 | 0.064 / 0.479 / 0.113 | 46/96 | 360 / 231 / 131 | 66 / 3 | 589 | 0.149 / 0.080 |
| 5. acronyms, headings *(unchanged)* | 0.786 | 0.735 | 0.128 / 0.479 / 0.202 | 0.064 / 0.479 / 0.113 | 46/96 | 360 / 231 / 131 | 66 / 3 | 589 | 0.149 / 0.080 |

#### hybrid

| Step | Ent F1 | Typed F1 | Rel typed P / R / F1 | Rel all P / R / F1 | Gold edges | Typed / generic / date | Dropped: unlisted / build unknown | Built | openrep typed F1 / all F1 |
|---|---|---|---|---|---|---|---|---|---|
| 0–1. baseline `c8aacd2a`, scored typed and all | 0.752 | 0.702 | 0.146 / 0.729 / 0.244 | 0.079 / 0.729 / 0.143 | 70/96 | 478 / 276 / 128 | 0 / 71 | 696 | 0.225 / 0.130 |
| 2. generic associations | 0.752 | 0.702 | 0.146 / 0.729 / 0.244 | 0.080 / 0.729 / 0.144 | 70/96 | 478 / 269 / 128 | 0 / 71 | 689 | 0.225 / 0.131 |
| 3a. listed endpoints (parser) | 0.754 | 0.703 | 0.153 / 0.719 / 0.252 | 0.085 / 0.719 / 0.153 | 69/96 | 452 / 233 / 123 | 65 / 5 | 692 | 0.232 / 0.140 |
| 3b. prompt rules (live replies) | 0.765 | 0.698 | 0.170 / 0.729 / 0.276 | 0.091 / 0.729 / 0.161 | 70/96 | 412 / 225 / 135 | 60 / 4 | 634 | 0.240 / 0.137 |
| 4. government ↔ country | 0.772 | 0.727 | 0.171 / 0.729 / 0.277 | 0.091 / 0.729 / 0.162 | 70/96 | 410 / 223 / 135 | 60 / 4 | 630 | 0.241 / 0.138 |
| 5. acronyms, headings | 0.772 | 0.728 | 0.171 / 0.729 / 0.277 | 0.091 / 0.729 / 0.162 | 70/96 | 409 / 223 / 135 | 60 / 3 | 630 | 0.241 / 0.138 |

#### Per set, first row and last

| Mode | Set | Ent F1 | Typed F1 | Rel typed P / R / F1 | Rel all P / R / F1 | Generic edges | Date links |
|---|---|---|---|---|---|---|---|
| nlp | openrep | 0.772 → 0.788 | 0.710 → 0.728 | 0.638 → 0.649 / 0.507 → 0.507 / 0.565 → 0.569 | 0.055 → 0.060 / 0.507 → 0.507 / 0.099 → 0.107 | 612 → 557 | 3 → 3 |
| nlp | kestrel | 0.910 → 0.910 | 0.656 → 0.656 | 1.000 → 1.000 / 0.200 → 0.200 / 0.333 → 0.333 | 0.039 → 0.040 / 0.200 → 0.200 / 0.066 → 0.067 | 49 → 48 | 0 → 0 |
| nlp | cyber | 0.960 → 0.960 | 0.960 → 0.960 | 1.000 → 1.000 / 0.615 → 0.615 / 0.762 → 0.762 | 0.210 → 0.210 / 0.615 → 0.615 / 0.314 → 0.314 | 30 → 30 | 0 → 0 |
| nlp | **combined** | 0.799 → 0.812 | 0.716 → 0.731 | 0.691 → 0.702 / 0.490 → 0.490 / 0.573 → 0.577 | 0.062 → 0.067 / 0.490 → 0.490 / 0.110 → 0.117 | 691 → 635 | 3 → 3 |
| llm | openrep | 0.740 → 0.759 | 0.683 → 0.707 | 0.079 → 0.091 / 0.397 → 0.397 / 0.131 → 0.149 | 0.040 → 0.044 / 0.397 → 0.397 / 0.073 → 0.080 | 230 → 207 | 123 → 128 |
| llm | kestrel | 0.865 → 0.890 | 0.772 → 0.823 | 0.114 → 0.316 / 0.400 → 0.600 / 0.178 → 0.414 | 0.051 → 0.143 / 0.400 → 0.600 / 0.091 → 0.231 | 41 → 21 | 2 → 2 |
| llm | cyber | 0.949 → 0.961 | 0.949 → 0.961 | 0.423 → 0.458 / 0.846 → 0.846 / 0.564 → 0.595 | 0.344 → 0.393 / 0.846 → 0.846 / 0.489 → 0.537 | 5 → 3 | 1 → 1 |
| llm | **combined** | 0.767 → 0.786 | 0.708 → 0.735 | 0.102 → 0.128 / 0.458 → 0.479 / 0.167 → 0.202 | 0.053 → 0.064 / 0.458 → 0.479 / 0.095 → 0.113 | 276 → 231 | 126 → 131 |
| hybrid | openrep | 0.724 → 0.743 | 0.677 → 0.700 | 0.132 → 0.145 / 0.753 → 0.726 / 0.225 → 0.241 | 0.071 → 0.076 / 0.753 → 0.726 / 0.130 → 0.138 | 230 → 199 | 125 → 132 |
| hybrid | kestrel | 0.861 → 0.886 | 0.768 → 0.819 | 0.114 → 0.316 / 0.400 → 0.600 / 0.178 → 0.414 | 0.051 → 0.143 / 0.400 → 0.600 / 0.091 → 0.231 | 41 → 21 | 2 → 2 |
| hybrid | cyber | 0.937 → 0.961 | 0.937 → 0.961 | 0.407 → 0.458 / 0.846 → 0.846 / 0.550 → 0.595 | 0.333 → 0.393 / 0.846 → 0.846 / 0.478 → 0.537 | 5 → 3 | 1 → 1 |
| hybrid | **combined** | 0.752 → 0.772 | 0.702 → 0.728 | 0.146 → 0.171 / 0.729 → 0.729 / 0.244 → 0.277 | 0.079 → 0.091 / 0.729 → 0.729 / 0.143 → 0.162 | 276 → 223 | 128 → 135 |

### The tasks

1. **Typed and all** (`0c057b2d`). The scoring rule above. It moves no
   prediction; it is what makes the rest measurable. On the baseline the
   typed figures were already far above all (nlp typed P 0.691 against
   0.062), because 691 of NLP's 762 edges are generic.
2. **Generic associations only in a shared sentence, with nothing typed
   between the pair** (`f422b676`, and the prompt half in `0fad4a12`). NLP
   held each co-occurrence edge until the whole text had been read, so a pair
   a later sentence (or the ship-of-unit pass) relates by type no longer keeps
   a generic edge as well; and both ends must be named in one paragraph of
   spaCy's sentence, which had joined headings to the text under them ("China"
   over "In addition, South Korea ..."). The parser drops a model
   `ASSOCIATED_WITH` on a pair an asserted typed edge links, in `llm` and
   again after the hybrid merge (the model's Russia `ASSOCIATED_WITH` Ukraine
   beside NLP's `TARGETS`), counted as `generic_on_typed_pair`. Generic edges
   on the old replies: nlp 691 → 648, llm 276 → 271, hybrid 276 → 269; typed
   recall did not move in any mode (0.490 / 0.458 / 0.729).
3. **Endpoints must be listed entities** (`8a13960c` parser, `0fad4a12`
   prompt). The parser resolves each model endpoint to a listed entity by
   name or alias (case and spacing aside, the key the hybrid merge matches by)
   and drops the rest, counted as `unlisted_endpoint` on the extraction result
   (`ExtractionResult.relationships_dropped_by_reason`, also in `meta`). In
   hybrid the check runs after the merge, so an endpoint only NLP extracted
   resolves and that entity joins the merged set. Events named only in their
   date link are still minted first. On the old replies llm dropped 68 edges
   and the build's unknown-endpoint drops fell 75 → 4 (hybrid 71 → 5). Two
   gold edges went with them, both of which the eval had counted and the build
   had dropped: NATO `DEPLOYED_AT` Europe in `llm` (the model never listed
   Europe; hybrid keeps it through NLP's Europe) and "Russian personnel"
   `DEPLOYED_AT` Mali.

   The prompt now states both relationship rules, with a negative example
   for `ASSOCIATED_WITH` (names from no corpus; a test checks the openrep gold
   too). Its geopolitical example broke both rules it states, dating a
   "Mozdok deployment" it never listed on a date its text does not give, and
   pointed `COMMANDED_BY` from the person to the unit; fixed, and a test
   holds every example in the prompt to the rules. **The prompt moved the
   model less than the parser does**: on the live replies the model still
   named 66 unlisted endpoints (68 on the old prompt) and emitted 232 generic
   edges (234), though kestrel's generic edges halved (39 → 21). Typed
   precision rose in both model modes (llm 0.104 → 0.127, hybrid 0.153 →
   0.170), but this row also changes the sample: gold edges were found in
   one sample and not the other (lost, among others: the three E3 memberships,
   Israel and the United States `TARGETS` Iran, Kaohsiung `LOCATED_AT`
   Taiwan; found: Volt Typhoon `TARGETS` Guam, two kestrel berths, GCHQ
   `BELONGS_TO` the United Kingdom, Ukraine `TARGETS` Russia).
4. **Government ↔ country** (`9293337a`). `data/governments.yaml` lists 29
   countries with their names, demonyms, extra forms (the Kremlin) and
   capitals, and the templates that make government forms ("{adjective}
   government", "government of {name}", "{name} regime", ...). Extraction
   (NLP, llm, and the hybrid merge) puts every Location or Organization the
   table resolves to one country into one entity, named as the text names the
   country, with the other forms as aliases, typed Location as the gold types
   countries; edges follow and a self-edge is counted as `same_entity`. A
   capital joins only when the text uses it as the state more often than as a
   place, read from the parse: "Tehran asserts ...", "Beijing's insistence",
   "the regimes in Minsk and Moscow" against "discussions in Tehran", "two
   secret visits to Beijing". `graph_builder` resolves a country name or
   government form to the country's node under the table's name (and looks
   the written name up too, for a node an earlier build made); a capital only
   when it arrives typed as an organization, since the build has no text.
   Location nodes carry no alias field (`models/entities.py`), so in the
   graph the form is resolved, not stored. On identical replies: typed entity
   F1 llm 0.707 → 0.735, hybrid 0.698 → 0.727 (the model had typed countries
   Organization), entity F1 nlp 0.799 → 0.806; 13 NLP extras gone ("Tehran",
   "Moscow", "Minsk", "Beijing", "Taipei", "China" beside "PRC"), and no gold
   entity newly missed in any mode.
5. **Acronyms and headings** (`26704091`). `known_entities.yaml` gains
   `proper_name_acronyms` (treaties and acts, combatant commands, CFIUS,
   MTCR), extracted wherever the text writes one as a word, typed from the
   list, with the text's definition as alias; one already inside an extracted
   name ("the FY2026 NDAA") is not extracted again. JCPOA is now found in all
   three documents that name it. A heading is a line all in title case
   without a closing full stop, or one that opens with an imperative; the
   openrep products write their tasking as a run-in title after a dash
   ("Prior product … — Assess Russian hybrid warfare …", which ends with a
   full stop), so that counts too. A spaCy span on a heading that starts on
   the imperative or begins or ends on a small word is dropped ("Assess
   Russian", "Assess Arctic", "Assess", "Toward Taiwan", "PRC Influence
   and"), and a span across a line break is never a name (eight openrep
   spans such as "Neighbors\n\nKuwait"). NLP entity F1 0.806 → 0.812. Two
   openrep gold entities are newly missed, USS Ponce and FREMM: the eval had
   matched them by substring to "USS Ponce\n\nSource" and "Design Compared to
   FREMM Design\n\nSource", names the graph build discards as junk.

### Regression check on the older sets (NLP)

| Step | legacy F1 (P / R) | legacy typed F1 | holdout F1 (P / R) | holdout typed F1 | rel all F1 legacy / holdout | rel typed F1 legacy / holdout |
|---|---|---|---|---|---|---|
| 0–1. baseline `c8aacd2a` | 0.546 (0.394 / 0.893) | 0.461 | 0.736 (0.632 / 0.882) | 0.515 | 0.018 / 0.013 | 0.061 / 0.046 |
| 2. generic associations | 0.546 (0.394 / 0.893) | 0.461 | 0.736 (0.632 / 0.882) | 0.515 | 0.020 / 0.015 | 0.061 / 0.046 |
| 4. government ↔ country | 0.547 (0.395 / 0.893) | 0.462 | 0.741 (0.638 / 0.882) | 0.518 | 0.020 / 0.015 | 0.061 / 0.046 |
| 5. acronyms, headings | 0.548 (0.396 / 0.890) | 0.462 | 0.733 (0.634 / 0.868) | 0.522 | 0.020 / 0.015 | 0.061 / 0.046 |

Step 5's holdout dip is one gold entity, GLACIER CIRCUIT, credited until now
through the junk span "GLACIER CIRCUIT\n\nReport ID"; the all-capitals filter
drops the name where the body writes it. Legacy lost Bank of East Asia the
same way ("Financial Flows\n\nBank of East Asia"), shed four junk spans of
that kind, and gained an extra (CENTCOM, which that gold omits). Step 4 resolved "the coordination between
Moscow and Tehran" to Russia and Iran.

### Still open after this phase

- **The model does not follow the relationship rules.** On the live replies
  it named 66 endpoints it never listed and emitted 231 generic edges (207
  in openrep, 32% of its openrep edges). The parser enforces the endpoint
  rule; for generic edges it enforces only "not beside a typed edge" (the
  "same sentence" half is a prompt instruction for the model, enforced in
  NLP only), because checking a model edge against sentences means matching
  names to text, which coreference defeats ("the group", "the system").
  Generic edges from the model carry its confidence, mostly above
  `cooccurrence_confidence_min`, so they reach the graph.
- **Date links still carry events the model writes as sentences** ("Japan
  Tomahawk delivery delay", "OFAC wind-down of Iranian-origin carpets"), and
  an event named only in its date link is still minted, so those edges are
  kept by design (the timeline depends on them).
- **A span across a line break is dropped, not split.** Splitting it would
  recover Bank of East Asia but also keep "Source", "Report ID" and "Stage 1 -
  Loader"; not done.
- **Capitals in the graph build.** Without text, the build resolves a capital
  only when it is typed as an organization; a capital extraction left as a
  Location (a place, or a text it could not parse) stays one.
- NLP's remaining extras are the previous phase's: administrations, "U.S.
  forces", fiscal-year labels.

## openrep phase (2026-09-30): before and after, one fix at a time

Each row is that commit's extraction code re-measured with the final runner,
scorer and gold on the same replayed replies. Step 0 is therefore not the
committed baseline's llm/hybrid F1 (0.698 / 0.688): the gold gained the
written forms of the executive orders afterwards (`d9daadac`, a gold
correction, not a fix). The `openrep` columns are that set alone. "All sets"
is the combined row. "Built / Dropped" are graph-build totals over the three
sets. *(unchanged)* means the step did not touch that mode. At step 0 one
document is degraded in `llm` and `hybrid` (the cut-off reply, scored as
what ran: NLP); from step 1 none is.

#### nlp

| Step | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Gold edges | All sets: ent F1 / typed F1 / rel F1 | Built | Dropped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0. baseline `f6369098` | 0.630 | 0.923 | 0.749 | 0.655 | 0.875 | 0.001 | 0.014 | 0.003 | 1/73 | 0.779 / 0.670 / 0.025 | 17 | 13 |
| 1. repeated keys, cut-off replies *(unchanged)* | 0.630 | 0.923 | 0.749 | 0.655 | 0.875 | 0.001 | 0.014 | 0.003 | 1/73 | 0.779 / 0.670 / 0.025 | 17 | 13 |
| 2. possessives, titles, action nouns; _BY verbs | 0.630 | 0.923 | 0.749 | 0.655 | 0.875 | 0.047 | 0.452 | 0.085 | 33/73 | 0.779 / 0.670 / 0.097 | 65 | 13 |
| 3. acronym bodies, documents | 0.623 | 0.947 | 0.752 | 0.671 | 0.892 | 0.045 | 0.466 | 0.083 | 34/73 | 0.781 / 0.683 / 0.094 | 66 | 13 |
| 4. designators, exercises, waterways | 0.626 | 0.947 | 0.754 | 0.681 | 0.903 | 0.046 | 0.466 | 0.083 | 34/73 | 0.783 / 0.691 / 0.095 | 65 | 13 |
| 5. abstract model types, ship classes *(unchanged)* | 0.626 | 0.947 | 0.754 | 0.681 | 0.903 | 0.046 | 0.466 | 0.083 | 34/73 | 0.783 / 0.691 / 0.095 | 65 | 13 |
| 6. head word decides | 0.626 | 0.947 | 0.754 | 0.695 | 0.921 | 0.046 | 0.466 | 0.083 | 34/73 | 0.783 / 0.703 / 0.095 | 64 | 13 |
| 7. bracketed acronyms are aliases | 0.651 | 0.947 | 0.772 | 0.709 | 0.919 | 0.055 | 0.507 | 0.099 | 37/73 | 0.798 / 0.715 / 0.109 | 67 | 11 |
| 8. the model's aliases in the hybrid merge | 0.652 | 0.947 | 0.772 | 0.710 | 0.919 | 0.055 | 0.507 | 0.099 | 37/73 | 0.799 / 0.716 / 0.110 | 67 | 11 |
| 9. a kept NLP edge keeps its endpoint *(unchanged)* | 0.652 | 0.947 | 0.772 | 0.710 | 0.919 | 0.055 | 0.507 | 0.099 | 37/73 | 0.799 / 0.716 / 0.110 | 67 | 11 |

#### llm

| Step | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Gold edges | All sets: ent F1 / typed F1 / rel F1 | Built | Dropped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0. baseline `f6369098` | 0.588 | 0.902 | 0.712 | 0.641 | 0.900 | 0.034 | 0.343 | 0.061 | 25/73 | 0.745 / 0.674 / 0.084 | 649 | 74 |
| 1. repeated keys, cut-off replies | 0.595 | 0.937 | 0.728 | 0.661 | 0.908 | 0.038 | 0.397 | 0.070 | 29/73 | 0.757 / 0.690 / 0.092 | 676 | 76 |
| 2. possessives, titles, action nouns; _BY verbs *(unchanged)* | 0.595 | 0.937 | 0.728 | 0.661 | 0.908 | 0.038 | 0.397 | 0.070 | 29/73 | 0.757 / 0.690 / 0.092 | 676 | 76 |
| 3. acronym bodies, documents *(unchanged)* | 0.595 | 0.937 | 0.728 | 0.661 | 0.908 | 0.038 | 0.397 | 0.070 | 29/73 | 0.757 / 0.690 / 0.092 | 676 | 76 |
| 4. designators, exercises, waterways | 0.595 | 0.937 | 0.728 | 0.669 | 0.918 | 0.038 | 0.397 | 0.070 | 29/73 | 0.757 / 0.696 / 0.092 | 676 | 76 |
| 5. abstract model types, ship classes | 0.611 | 0.937 | 0.740 | 0.683 | 0.923 | 0.040 | 0.397 | 0.073 | 29/73 | 0.767 / 0.708 / 0.095 | 649 | 75 |
| 6. head word decides *(unchanged)* | 0.611 | 0.937 | 0.740 | 0.683 | 0.923 | 0.040 | 0.397 | 0.073 | 29/73 | 0.767 / 0.708 / 0.095 | 649 | 75 |
| 7. bracketed acronyms are aliases *(unchanged)* | 0.611 | 0.937 | 0.740 | 0.683 | 0.923 | 0.040 | 0.397 | 0.073 | 29/73 | 0.767 / 0.708 / 0.095 | 649 | 75 |
| 8. the model's aliases in the hybrid merge *(unchanged)* | 0.611 | 0.937 | 0.740 | 0.683 | 0.923 | 0.040 | 0.397 | 0.073 | 29/73 | 0.767 / 0.708 / 0.095 | 649 | 75 |
| 9. a kept NLP edge keeps its endpoint *(unchanged)* | 0.611 | 0.937 | 0.740 | 0.683 | 0.923 | 0.040 | 0.397 | 0.073 | 29/73 | 0.767 / 0.708 / 0.095 | 649 | 75 |

#### hybrid

| Step | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Gold edges | All sets: ent F1 / typed F1 / rel F1 | Built | Dropped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0. baseline `f6369098` | 0.557 | 0.941 | 0.700 | 0.638 | 0.912 | 0.033 | 0.343 | 0.061 | 25/73 | 0.732 / 0.670 / 0.084 | 652 | 71 |
| 1. repeated keys, cut-off replies | 0.557 | 0.963 | 0.706 | 0.650 | 0.921 | 0.038 | 0.397 | 0.070 | 29/73 | 0.737 / 0.679 / 0.091 | 679 | 73 |
| 2. possessives, titles, action nouns; _BY verbs | 0.557 | 0.963 | 0.706 | 0.650 | 0.921 | 0.065 | 0.712 | 0.119 | 52/73 | 0.737 / 0.679 / 0.133 | 714 | 82 |
| 3. acronym bodies, documents | 0.547 | 0.963 | 0.698 | 0.642 | 0.921 | 0.065 | 0.712 | 0.118 | 52/73 | 0.730 / 0.672 / 0.132 | 716 | 81 |
| 4. designators, exercises, waterways | 0.547 | 0.963 | 0.698 | 0.650 | 0.931 | 0.065 | 0.712 | 0.119 | 52/73 | 0.730 / 0.678 / 0.133 | 715 | 81 |
| 5. abstract model types, ship classes | 0.560 | 0.963 | 0.708 | 0.662 | 0.935 | 0.067 | 0.712 | 0.123 | 52/73 | 0.739 / 0.689 / 0.137 | 688 | 80 |
| 6. head word decides | 0.560 | 0.963 | 0.708 | 0.662 | 0.935 | 0.068 | 0.712 | 0.123 | 52/73 | 0.739 / 0.689 / 0.137 | 688 | 79 |
| 7. bracketed acronyms are aliases | 0.567 | 0.963 | 0.714 | 0.667 | 0.935 | 0.071 | 0.753 | 0.130 | 55/73 | 0.744 / 0.693 / 0.143 | 689 | 79 |
| 8. the model's aliases in the hybrid merge | 0.579 | 0.961 | 0.722 | 0.676 | 0.937 | 0.071 | 0.753 | 0.130 | 55/73 | 0.751 / 0.701 / 0.143 | 690 | 78 |
| 9. a kept NLP edge keeps its endpoint | 0.579 | 0.969 | 0.724 | 0.677 | 0.935 | 0.071 | 0.753 | 0.130 | 55/73 | 0.752 / 0.702 / 0.143 | 696 | 71 |

### The openrep fixes

1. **A reply that repeats its keys or is cut off keeps what it extracted.**
   One reply closed with `"relationships": [], "entities": []` after its full
   lists; `json.loads` keeps the last duplicate, so 17 entities read as none
   (a success-shaped zero, not even a degradation). Another ran past the
   token limit and degraded to NLP. `services/llm_output.py` gained
   `json_object(..., merge_duplicate_lists=True)` (off by default) and
   `json_array_items(content, key)`, and extraction uses both.
2. **Relations written as possessives, titles and action nouns; `_BY` verbs
   the right way round.** Analytic prose rarely states a relation as
   subject-verb-object. Each of these patterns now gives an edge:
   - "Poland's Internal Security Agency" → BELONGS_TO;
   - "European Commission President Ursula von der Leyen" and "Kaja Kallas,
     High Representative of the European Union" → BELONGS_TO;
   - "General Grynkewich, Commander of U.S. European Command" →
     COMMANDED_BY;
   - "Russian President Vladimir Putin" binds to a country of the text;
   - "invasion of", "strikes on", "war against" → TARGETS, and "military
     presence in" → DEPLOYED_AT;
   - "Iran-backed Houthi movement" → FUNDED_BY.

   SUPPLIED_BY, FUNDED_BY and COMMANDED_BY now point from the recipient
   ("Iran transferred missiles to Russia" → Russia SUPPLIED_BY Iran), and the
   passive is read through its agent. The verb map had read "X led Y" as X
   COMMANDED_BY Y. A subject phrase binds the name compounded with its head
   noun first, so "Iran-backed Houthi movement has attacked" is the Houthis.
   `relationship_types.yaml`: transfer and sell → SUPPLIED_BY.
3. **One-word acronyms are kept; executive orders, NDAAs and acts are
   documents.** The all-caps heading filter had dropped every single-word
   acronym (NORTHCOM, GCHQ, OFAC). spaCy read "Executive Order (E.O.) 14186"
   as the date "14186" and "the FY2026 NDAA" as a facility. *Cost:* hybrid
   entity precision fell (0.557 → 0.547), because NLP now kept acronyms the
   model had under their full names. Steps 7 and 8 take it back.
4. **Designators, exercises and waterways.** Ship-class designators (LHA,
   LPD, DDG, …) are now `Ship`, word-and-number designators (Qiam-1,
   Fateh-110) are `Weapon`, and "Operation X" or a name before "exercise" is
   an `Event`. Known multi-word places ("Strait of Hormuz") are extracted
   whole instead of as "Strait of" plus a person "Hormuz".
5. **The model's abstract types; ship classes.** Entities the model filed
   under types outside the vocabulary are dropped with their edges: "B2
   [Indicator]", "fissile material [Material]", "European security
   [Concept]", "Commercial reporting [DataSource]". "Constellation-class
   frigate [Equipment]" is a `Ship`.
6. **The head word decides the type.** A name ending in a weapon noun is a
   `Weapon` ("Hypersonic Cruise Missile"). One ending in an organization
   word is an `Organization`, so "Kuwait Gulf Oil Company" is no longer a
   place because it contains "Gulf".
7. **An acronym defined in brackets is the same entity.** "Office of Foreign
   Assets Control (OFAC)" makes OFAC an alias, not a second node. Mentions
   match by alias, so "Within DOD, the Army …" binds to the Department of
   Defense. A trailing 's is stripped from names ("Department of the
   Treasury's"). It also recovered the legacy and holdout F1 that step 3
   cost (below).
8. **Hybrid matches a name the model gave as an alias.** The merge looked
   NLP names up among the model's names only. With the model returning "U.S.
   Navy" (alias "Navy"), "Department of Defense" (alias "DOD") and
   "Executive Order 14347" (alias "E.O. 14347"), each NLP form was added as a
   second node. NLP also extracts an executive order once, with its other
   written forms as aliases. One gold miss is new: the model's "U.S.
   Department of Homeland Security" (alias "DHS") absorbs NLP's "DHS", and
   the scorer matches a prediction by its name, not its aliases.
9. **A kept NLP edge keeps its endpoint.** Hybrid kept NLP's typed edges
   but only NLP entities that are regex values or scored 0.8, so "Guetlein
   BELONGS_TO U.S. Space Force" survived the merge without the Space Force.
   The eval counted that edge as found, but the graph build dropped it.
   Eight hybrid edges were like this, two of them gold; none are now. The
   66 model edges naming something the model did not list as an entity
   ("Ukrainian forces", "31 larger amphibious ships") are left to the
   build to drop. Cyber F1 dips (0.949 → 0.937): NLP's "Windows" now takes
   the gold match the scorer had given the model's "built-in Windows
   tools", which becomes an extra, and the Volt Typhoon USES Windows edge
   now survives the build.

**Tried and reverted:** extracting every "Full Name (ACR)" definition as an
entity, even when spaCy missed the name. It cost openrep NLP entity F1
(0.772 → 0.768) and legacy (0.546 → 0.541). It found spurious definitions
("Fiscal Year (FY)", "Foreign Assets Control" without its "Office of") and
duplicates, so it was not committed.

### Regression check on the older sets (NLP)

| Step | legacy F1 (P / R) | legacy typed F1 | holdout F1 (P / R) | holdout typed F1 | rel F1 legacy / holdout |
|---|---|---|---|---|---|
| 0. baseline | 0.538 (0.385 / 0.890) | 0.453 | 0.736 (0.632 / 0.882) | 0.515 | 0.014 / 0.013 |
| 2. phrase relations | 0.538 (0.385 / 0.890) | 0.453 | 0.736 (0.632 / 0.882) | 0.515 | 0.018 / 0.013 |
| 3. acronym bodies, documents | 0.534 (0.381 / 0.893) | 0.451 | 0.723 (0.612 / 0.882) | 0.506 | 0.017 / 0.013 |
| 4. designators, exercises, waterways | 0.534 (0.381 / 0.893) | 0.451 | 0.723 (0.612 / 0.882) | 0.506 | 0.017 / 0.012 |
| 6. head word decides | 0.534 (0.381 / 0.893) | 0.451 | 0.723 (0.612 / 0.882) | 0.506 | 0.017 / 0.012 |
| 7. bracketed acronyms are aliases | 0.546 (0.394 / 0.893) | 0.461 | 0.736 (0.632 / 0.882) | 0.515 | 0.018 / 0.013 |
| 8.–9. hybrid merge (NLP: one document per order) | 0.546 (0.394 / 0.893) | 0.461 | 0.736 (0.632 / 0.882) | 0.515 | 0.018 / 0.013 |
| tried and reverted: acronym definitions | 0.541 (0.388 / 0.897) | 0.457 | 0.736 (0.632 / 0.882) | 0.515 | 0.018 / 0.013 |

Steps 1 and 5 do not touch NLP. The step 3 dip was real acronym bodies
those golds omit (MOIS, EUCOM, AIRCOM, KKBC) or list only under a full name
(NCIA); step 7 merged them into the names they abbreviate.

`kestrel` and `cyber` are in every row above. Across the phase, `kestrel`
is unchanged in every mode. `cyber` NLP entity F1 rose (0.946 → 0.960, "ASUS"
at step 3), and cyber hybrid moved only at step 9.

### Known remaining errors in openrep

*As the openrep phase left them. The extraction-precision phase above addressed the generic
associations, the unlisted endpoints, the country under two names and the NLP misses; see
"Still open after this phase" there for what remains. The build has counted its
below-threshold `ASSOCIATED_WITH` drops (`below_cooccurrence_min`) since the post-review
hardening.*

- **Relationship precision is low in every mode** (0.04–0.07). Of the
  model's 722 openrep edges, 230 are `ASSOCIATED_WITH` and 122 are
  `OCCURRED_ON` to a date, and the gold labels neither. Many of the dates
  belong to events the model writes as sentences ("Traoré visited Russia",
  "Nixon took office"; 56 extra Events). Those carry the timeline, so they
  are not filtered.
- **The model names edge endpoints it never lists as entities**: 66 of
  hybrid's 882 edges on the three sets ("Ukrainian forces", "U.S. military
  operations"). The graph build drops and counts them.
- **Administrations and group descriptions** ("Trump Administration",
  "U.S. forces", "NATO officials") are extras under the gold's policy.
  Filtering them would fit the extractor to the labeller, so it is not done.
- **A country under two names** when the model names the government ("PRC
  government") and NLP the country ("China", "PRC").
- **NLP misses** JCPOA, and it cuts names out of headings and run-in titles
  ("PRC Influence and", "Presidential Order required ByteDance").
- **The build drops below-threshold `ASSOCIATED_WITH` edges without counting
  them.** `graph_builder` discards such edges (under
  `cooccurrence_confidence_min`, 0.55) silently. Its "Dropped" count is
  only the edges naming an entity that was never extracted.

## Phase 1: kestrel and cyber

The first phase scored `kestrel` (then `corpus`) and `cyber` together. Its
numbers are the two sets combined, as they were committed then; the
"combined" rows above add `openrep` and are not comparable with them.

### Results at the end of phase 1 (live Cohere `command-a-plus-05-2026`)

| Mode | Entity P / R / F1 | Typed F1 | Type acc | Rel P / R / F1 | Cyber gold edges | Build: created / dropped |
|---|---|---|---|---|---|---|
| nlp | 0.924 / 0.917 / 0.920 | 0.738 | 0.802 | 0.115 / 0.435 / 0.182 | 8 / 13 | 10 / 0 |
| llm | 0.807 / 0.985 / 0.887 | 0.819 | 0.923 | 0.136 / 0.652 / 0.226 | 11 / 13 | 104 / 4 |
| hybrid | 0.760 / 0.985 / 0.858 | 0.805 | 0.939 | 0.149 / 0.739 / 0.248 | 11 / 13 | 110 / 2 |

No document degraded and no build raised in any of the three. `nlp` and
`hybrid` were run at `ef68988d`; `llm` at `a5954597`, and its recorded
replies replayed at `ef68988d` give identical numbers (the two later commits
touch neither path those replies exercise). The `llm` run's replies are the
ones in `llm_replies.json`; the `hybrid` run asked the model separately
(`--no-cache`), so its model half is a different sample — which is why its
relationship recall differs from `llm`'s.

The repo-root key is a Cohere trial key (20 calls a minute). A first final
`hybrid` run at concurrency 4 degraded four documents to NLP on 429s, which
the report flagged at the top; the runner now waits out a rate limit before
retrying, and the committed run used `--concurrency 2 --retries 3`.

### Phase 1 before and after, one fix at a time

Every row uses the corrected matcher (below) and, for `llm` and `hybrid`, the
same recorded replies — except step 8, which changed the prompt and so needed
new ones (live; the model is sampled, so step 8 compares two samples, and the
final row is a third). A step marked *unchanged* did not touch that mode.
"Cyber edges" is gold relationships found in the three live-run documents;
"AW share" the fraction of predicted edges that are `ASSOCIATED_WITH`;
"Built / Dropped / Orphan dates" are from the real graph build.

#### nlp

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

#### llm

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

#### hybrid

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
| **final, live** | 0.760 | 0.985 | 0.858 | 0.805 | 0.939 | 0.149 | 0.739 | 0.248 | 11/13 | 28% | 110 | 2 | 0 |

Hybrid's NLP half did gain typed edges at step 3, but the model already had
each of them, so the merged set did not change.

#### The phase 1 fixes

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
   meaning in the vocabulary is no longer stored as `ASSOCIATED_WITH` but
   dropped and counted in the log. *Narrowed in step 10.*
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
10. **Only reporting statements are dropped** — the full unit suite caught
    step 4 dropping "A PARTNERS_WITH B" ("A and B signed a partnership
    agreement"), a real relationship the vocabulary has no word for. Now only
    types that state something about the reporting (REPORTED, OBSERVED,
    IDENTIFIED, DOES_NOT_ESTABLISH, BASED_ON, …; 41 of the 43 off-vocabulary
    edges in the baseline replies) are dropped, and any other unlisted type
    stays `ASSOCIATED_WITH`. On the final prompt's replies this changes
    nothing; on the baseline prompt's replies, with every other fix applied,
    it costs a little:

    | Replies | Rel P | Rel F1 | AW share | Built |
    |---|---|---|---|---|
    | baseline prompt, step 4 rule (all fixes but the prompt) | 0.053 | 0.096 | 42% | 234 |
    | baseline prompt, step 10 rule | 0.050 | 0.092 | 44% | 245 |
    | final prompt, either rule (llm) | 0.136 | 0.226 | 42% | 104 |

Not a metric row: a model-returned indicator is stored refanged
("evil-c2[.]com" → "evil-c2.com"). Two live runs died in the graph build on
the bracket (`urlsplit` raises "Invalid IPv6 URL" in
`graph_builder._host_of`); the replies were lost with the runs, so the fix is
pinned by a unit test of that reply shape.

#### Phase 1 regression check on the older sets (NLP)

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

### The matcher bug this found

`extraction_eval._entity_matches` took the shorter and longer name with
`min()` and `max()`, which return the same argument when the lengths tie, so
the substring rule found a name inside itself: "Quay 4" matched "Torvik",
"Sarn" matched "Mira". Every eval built on it counted such pairs. Fixed
(`8e850822`); with it, the baseline LLM relationship recall is 0.565, not the
0.783 the first committed run reported, and every number above uses the fixed
matcher.

### Known remaining errors in kestrel and cyber

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
