# Corpus extraction eval — `llm`

Generated 2026-10-01T02:54:44+00:00 at `a5954597`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (43 live replies, 0 replayed).

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.807 | 0.985 | 0.887 | 130 | 161 | 132 |
| Entities (name + type) | 0.745 | 0.909 | 0.819 | 120 | 161 | 132 |
| Relationships | 0.136 | 0.652 | 0.226 | 15 | 110 | 23 |
| corpus: entities | 0.762 | 1.000 | 0.865 | 93 | 122 | 93 |
| corpus: entities typed | 0.680 | 0.892 | 0.772 | 83 | 122 | 93 |
| corpus: relationships | 0.051 | 0.400 | 0.091 | 4 | 78 | 10 |
| cyber: entities | 0.949 | 0.949 | 0.949 | 37 | 39 | 39 |
| cyber: entities typed | 0.949 | 0.949 | 0.949 | 37 | 39 | 39 |
| cyber: relationships | 0.344 | 0.846 | 0.489 | 11 | 32 | 13 |

Type accuracy on matched entities: **0.923** (parent category: 0.923). Gold relationship pairs connected by any edge: 21 of 23. ASSOCIATED_WITH share of predicted edges: 41.8%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Date | 1.000 | 0.667 | 0.800 | 2 | 2 | 3 |
| Document | 0.333 | 1.000 | 0.500 | 1 | 3 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Event | 0.000 | 0.000 | 0.000 | 0 | 20 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.786 | 1.000 | 0.880 | 33 | 42 | 33 |
| Organization | 0.976 | 0.976 | 0.976 | 40 | 41 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Ship | 0.968 | 0.750 | 0.845 | 30 | 31 | 40 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Person: 7
- Ship -> Location: 3

## Relationships

Predicted types: ASSOCIATED_WITH 46, LOCATED_AT 15, TARGETS 13, USES 9, MENTIONED_IN 8, BELONGS_TO 6, OCCURRED_ON 3, ATTRIBUTED_TO 2, EXPLOITS 2, COMMUNICATES_WITH 2, DEPLOYED_AT 2, SUPPLIED_BY 1, RESOLVES_TO 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 1 | 1 |
| EXPLOITS | 1 | 1 |
| LOCATED_AT | 4 | 10 |
| TARGETS | 3 | 5 |
| USES | 4 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 104, retired 2, dropped 4 {'LOCATED_AT': 2, 'ASSOCIATED_WITH': 2}; entities created 159, filtered 0, dates orphaned 0.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date]
- extra: CISA and NSA joint advisory [Event], living-off-the-land [TTP]
- edges: CISA -ASSOCIATED_WITH-> NSA; CISA and NSA joint advisory -OCCURRED_ON-> 24 May 2023; Microsoft -ASSOCIATED_WITH-> Volt Typhoon; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -COMMUNICATES_WITH-> 185.220.101.42; Volt Typhoon -COMMUNICATES_WITH-> evil-c2.com; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -USES-> living-off-the-land
- gold edges missed: none
- build: created 8, dropped 0 {}

### volt_typhoon_2

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: CVE-2023-27997 -TARGETS-> Fortinet FortiGuard; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> ASUS; Volt Typhoon -USES-> Cisco; Volt Typhoon -USES-> Netgear; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 11, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: none
- edges: Kaohsiung -LOCATED_AT-> Taiwan; Microsoft -ASSOCIATED_WITH-> Volt Typhoon; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE router -RESOLVES_TO-> 45.83.12.7; Netgear ProSAFE router -USES-> Volt Typhoon; Volt Typhoon -ASSOCIATED_WITH-> Naval Base Guam; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -LOCATED_AT-> Guam networks; Volt Typhoon -TARGETS-> Asia; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> built-in Windows tools
- gold edges missed: Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 12, dropped 0 {}

## Corpus: most frequent misses and extras

Missed: none.

Extra: Valdorian [Location] x2, EXERCISE — FICTIONAL [Event] x1, Quay 4 [Location] x1, Comparison against imagery of 3 days earlier [Event] x1, Imagery establishes presence and disposition [Event] x1, Imagery of Torvik collected during the period [Event] x1, Observed dispersal pattern [Event] x1, EXERCISE — FICTIONAL [Document] x1, Collection at 1742Z [Event] x1, E03 [Document] x1, Loading activity [Event] x1, Sedne fuel uptake [Event] x1, apron [Location] x1, naval jetty [Location] x1, Escort tasking assignment [Event] x1.
