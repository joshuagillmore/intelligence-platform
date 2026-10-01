# Corpus extraction eval — `hybrid`

Generated 2026-10-01T03:19:46+00:00 at `ef68988d`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (43 live replies, 0 replayed).

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.760 | 0.985 | 0.858 | 130 | 171 | 132 |
| Entities (name + type) | 0.714 | 0.924 | 0.805 | 122 | 171 | 132 |
| Relationships | 0.149 | 0.739 | 0.248 | 17 | 114 | 23 |
| corpus: entities | 0.705 | 1.000 | 0.827 | 93 | 132 | 93 |
| corpus: entities typed | 0.651 | 0.925 | 0.764 | 86 | 132 | 93 |
| corpus: relationships | 0.072 | 0.600 | 0.129 | 6 | 83 | 10 |
| cyber: entities | 0.949 | 0.949 | 0.949 | 37 | 39 | 39 |
| cyber: entities typed | 0.923 | 0.923 | 0.923 | 36 | 39 | 39 |
| cyber: relationships | 0.355 | 0.846 | 0.500 | 11 | 31 | 13 |

Type accuracy on matched entities: **0.939** (parent category: 0.939). Gold relationship pairs connected by any edge: 18 of 23. ASSOCIATED_WITH share of predicted edges: 28.1%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Date | 1.000 | 0.667 | 0.800 | 2 | 2 | 3 |
| Document | 0.333 | 1.000 | 0.500 | 1 | 3 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Event | 0.000 | 0.000 | 0.000 | 0 | 19 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.821 | 0.970 | 0.889 | 32 | 39 | 33 |
| Organization | 0.800 | 0.976 | 0.879 | 40 | 50 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Ship | 0.971 | 0.825 | 0.892 | 33 | 34 | 40 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| System | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Technology | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Organization: 3
- Ship -> Location: 2
- Ship -> Person: 2
- Location -> Organization: 1

## Relationships

Predicted types: ASSOCIATED_WITH 32, LOCATED_AT 21, MENTIONED_IN 15, USES 13, BELONGS_TO 11, TARGETS 10, OCCURRED_ON 4, ATTRIBUTED_TO 2, EXPLOITS 2, COMMUNICATES_WITH 2, DEPLOYED_AT 1, RESOLVES_TO 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 1 | 1 |
| EXPLOITS | 1 | 1 |
| LOCATED_AT | 5 | 10 |
| TARGETS | 4 | 5 |
| USES | 4 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 110, retired 2, dropped 2 {'OCCURRED_ON': 1, 'USES': 1}; entities created 169, filtered 0, dates orphaned 0.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date]
- extra: CISA-NSA joint advisory [Event], living-off-the-land [TTP]
- edges: CISA-NSA joint advisory -OCCURRED_ON-> 24 May 2023; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -COMMUNICATES_WITH-> 185.220.101.42; Volt Typhoon -COMMUNICATES_WITH-> evil-c2.com; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -USES-> living-off-the-land
- gold edges missed: none
- build: created 6, dropped 0 {}

### volt_typhoon_2

- mistyped: People's Republic of China: Location -> Organization
- missed: CISA [Organization]
- extra: none
- edges: CVE-2023-27997 -TARGETS-> Fortinet FortiGuard; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> ASUS; Volt Typhoon -USES-> Cisco; Volt Typhoon -USES-> Fortinet FortiGuard; Volt Typhoon -USES-> Netgear; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 12, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: none
- edges: Microsoft -ASSOCIATED_WITH-> Volt Typhoon; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE router -LOCATED_AT-> Guam; Netgear ProSAFE router -RESOLVES_TO-> 45.83.12.7; Volt Typhoon -TARGETS-> Asia; Volt Typhoon -TARGETS-> Naval Base Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> Guam; Volt Typhoon -USES-> Kaohsiung; Volt Typhoon -USES-> Manila; Volt Typhoon -USES-> Windows; Volt Typhoon -USES-> built-in Windows tools
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 11, dropped 1 {'USES': 1}

## Corpus: most frequent misses and extras

Missed: none.

Extra: EXERCISE — FICTIONAL [Event] x3, Fictional Exercise [Event] x2, Valdorian naval liaison [Person] x2, crewed transport aircraft [Aircraft] x2, quay 4 [Location] x1, Exercise Fictional Report [Document] x1, Fictional Exercise Report [Event] x1, apron [Location] x1, naval jetty [Location] x1, Cancelled port calls at Torvik [Event] x1, Collection against the Meran Strait [Event] x1, GNSS [Technology] x1, central strait [Location] x1, transmitter site near the Meran coast [Location] x1, Interference cessation [Event] x1.
