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

## Results (committed)

`corpus_eval_{nlp,llm,hybrid}.{json,md}`, run at `719b9ca6` with
`--build-neo4j --concurrency 2 --retries 3`:

| Mode | Set | Ent P | Ent R | Ent F1 | Typed F1 | Type acc | Rel P | Rel R | Rel F1 | Gold edges found |
|---|---|---|---|---|---|---|---|---|---|---|
| nlp | openrep | 0.652 | 0.947 | 0.772 | 0.710 | 0.919 | 0.055 | 0.507 | 0.099 | 37/73 |
| nlp | kestrel | 0.896 | 0.925 | 0.910 | 0.656 | 0.721 | 0.039 | 0.200 | 0.066 | 2/10 |
| nlp | cyber | 1.000 | 0.923 | 0.960 | 0.960 | 1.000 | 0.210 | 0.615 | 0.314 | 8/13 |
| nlp | **combined** | 0.693 | 0.942 | 0.799 | 0.716 | 0.896 | 0.062 | 0.490 | 0.110 | 47/96 |
| llm | openrep | 0.611 | 0.937 | 0.740 | 0.683 | 0.923 | 0.040 | 0.397 | 0.073 | 29/73 |
| llm | kestrel | 0.762 | 1.000 | 0.865 | 0.772 | 0.892 | 0.051 | 0.400 | 0.091 | 4/10 |
| llm | cyber | 0.949 | 0.949 | 0.949 | 0.949 | 1.000 | 0.344 | 0.846 | 0.489 | 11/13 |
| llm | **combined** | 0.645 | 0.947 | 0.767 | 0.708 | 0.923 | 0.053 | 0.458 | 0.095 | 44/96 |
| hybrid | openrep | 0.579 | 0.969 | 0.724 | 0.677 | 0.935 | 0.071 | 0.753 | 0.130 | 55/73 |
| hybrid | kestrel | 0.756 | 1.000 | 0.861 | 0.768 | 0.892 | 0.051 | 0.400 | 0.091 | 4/10 |
| hybrid | cyber | 0.925 | 0.949 | 0.937 | 0.937 | 1.000 | 0.333 | 0.846 | 0.478 | 11/13 |
| hybrid | **combined** | 0.614 | 0.972 | 0.752 | 0.702 | 0.933 | 0.079 | 0.729 | 0.143 | 70/96 |

- **Same replies throughout.** `nlp` is deterministic. `llm` and `hybrid`
  replay `llm_replies.json`. The 40 `openrep` replies were asked live of
  Cohere `command-a-plus-05-2026` once, for the baseline (`f6369098`), and
  `kestrel` and `cyber` replay phase 1's. No fix in this phase changed the
  prompt, so no reply was asked for again and every row below compares the
  same model output.
- **`hybrid` replays the `llm` replies**, so its model half is the same
  sample as `llm`'s. Phase 1's `hybrid` asked separately (`--no-cache`), so
  its `kestrel` and `cyber` numbers are not these.
- No document degraded and no graph build raised.
- **Trial-key limits.** The repo-root key is a Cohere trial key: 20 calls a
  minute and 1,000 a month. Replaying is what makes a fix-by-fix record
  affordable on it.

## openrep: before and after, one fix at a time

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
