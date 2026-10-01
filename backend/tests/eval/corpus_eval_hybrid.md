# Corpus extraction eval — `hybrid`

Generated 2026-10-01T02:57:32+00:00 at `a5954597`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (43 live replies, 0 replayed).

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.774 | 0.985 | 0.867 | 130 | 168 | 132 |
| Entities (name + type) | 0.732 | 0.932 | 0.820 | 123 | 168 | 132 |
| Relationships | 0.136 | 0.652 | 0.226 | 15 | 110 | 23 |
| corpus: entities | 0.732 | 1.000 | 0.846 | 93 | 127 | 93 |
| corpus: entities typed | 0.677 | 0.925 | 0.782 | 86 | 127 | 93 |
| corpus: relationships | 0.062 | 0.500 | 0.111 | 5 | 80 | 10 |
| cyber: entities | 0.902 | 0.949 | 0.925 | 37 | 41 | 39 |
| cyber: entities typed | 0.902 | 0.949 | 0.925 | 37 | 41 | 39 |
| cyber: relationships | 0.333 | 0.769 | 0.465 | 10 | 30 | 13 |

Type accuracy on matched entities: **0.946** (parent category: 0.946). Gold relationship pairs connected by any edge: 19 of 23. ASSOCIATED_WITH share of predicted edges: 22.7%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Date | 1.000 | 0.667 | 0.800 | 2 | 2 | 3 |
| Document | 0.250 | 1.000 | 0.400 | 1 | 4 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Duration | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Event | 0.000 | 0.000 | 0.000 | 0 | 14 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Indicator | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Location | 0.868 | 1.000 | 0.930 | 33 | 38 | 33 |
| Organization | 0.870 | 0.976 | 0.919 | 40 | 46 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Ship | 1.000 | 0.825 | 0.904 | 33 | 33 | 40 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| System | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Technology | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Time | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Person: 4
- Ship -> Location: 2
- Ship -> Organization: 1

## Relationships

Predicted types: ASSOCIATED_WITH 25, LOCATED_AT 22, BELONGS_TO 13, TARGETS 11, USES 9, MENTIONED_IN 8, OCCURRED_ON 5, COMMUNICATES_WITH 4, ATTRIBUTED_TO 4, DEPLOYED_AT 4, SUPPLIED_BY 3, EXPLOITS 2.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 1 | 1 |
| EXPLOITS | 1 | 1 |
| LOCATED_AT | 4 | 10 |
| TARGETS | 3 | 5 |
| USES | 4 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 101, retired 2, dropped 7 {'LOCATED_AT': 6, 'MENTIONED_IN': 1}; entities created 166, filtered 0, dates orphaned 1.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date]
- extra: joint advisory [Document], living-off-the-land techniques [TTP]
- edges: CISA -ASSOCIATED_WITH-> NSA; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -COMMUNICATES_WITH-> 185.220.101.42; Volt Typhoon -COMMUNICATES_WITH-> evil-c2.com; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -USES-> living-off-the-land techniques; joint advisory -OCCURRED_ON-> 24 May 2023
- gold edges missed: none
- build: created 7, dropped 0 {}

### volt_typhoon_2

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: ASUS -SUPPLIED_BY-> Volt Typhoon; Cisco -SUPPLIED_BY-> Volt Typhoon; Fortinet FortiGuard -EXPLOITS-> CVE-2023-27997; Netgear -SUPPLIED_BY-> Volt Typhoon; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> Fortinet FortiGuard; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 11, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: Naval Base Guam intrusions [Event], Volt Typhoon pre-positioning [Event]
- edges: Microsoft -ATTRIBUTED_TO-> Volt Typhoon; NSA -BELONGS_TO-> United States; Naval Base Guam intrusions -TARGETS-> Naval Base Guam; Netgear ProSAFE router -LOCATED_AT-> 45.83.12.7; Netgear ProSAFE router -USES-> Volt Typhoon; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -LOCATED_AT-> Guam; Volt Typhoon -USES-> Windows; Volt Typhoon pre-positioning -TARGETS-> Asia; Volt Typhoon pre-positioning -TARGETS-> United States
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 11, dropped 0 {}

## Corpus: most frequent misses and extras

Missed: none.

Extra: EXERCISE — FICTIONAL [Document] x2, AIS [Technology] x2, Valdorian naval liaison [Person] x2, EXERCISE — FICTIONAL [Event] x1, Mirenda loading aggregate [Event] x1, Cancelled port calls at Torvik [Event] x1, Collection against Meran Strait [Event] x1, 5 affected sailings [Event] x1, 8 outlets [Organization] x1, 90 hours [Duration] x1, Central strait [Location] x1, Commercial and press reporting [Organization] x1, GNSS [Technology] x1, Merchant traffic [Organization] x1, transmitter site [Location] x1.
