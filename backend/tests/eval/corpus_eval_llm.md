# Corpus extraction eval — `llm`

Generated 2026-10-01T01:53:57+00:00 at `be263d08`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (43 live replies, 0 replayed).

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.339 | 0.985 | 0.504 | 130 | 384 | 132 |
| Entities (name + type) | 0.292 | 0.849 | 0.434 | 112 | 384 | 132 |
| Relationships | 0.054 | 0.783 | 0.101 | 18 | 334 | 23 |
| corpus: entities | 0.273 | 1.000 | 0.429 | 93 | 341 | 93 |
| corpus: entities typed | 0.235 | 0.860 | 0.369 | 80 | 341 | 93 |
| corpus: relationships | 0.024 | 0.700 | 0.046 | 7 | 296 | 10 |
| cyber: entities | 0.861 | 0.949 | 0.902 | 37 | 43 | 39 |
| cyber: entities typed | 0.744 | 0.821 | 0.780 | 32 | 43 | 39 |
| cyber: relationships | 0.289 | 0.846 | 0.431 | 11 | 38 | 13 |

Type accuracy on matched entities: **0.862** (parent category: 0.885). Gold relationship pairs connected by any edge: 21 of 23. ASSOCIATED_WITH share of predicted edges: 45.5%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Attack | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| DataSource | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Date | 0.043 | 0.667 | 0.082 | 2 | 46 | 3 |
| Document | 0.000 | 0.000 | 0.000 | 0 | 4 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Duration | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 13 | 0 |
| Event | 0.000 | 0.000 | 0.000 | 0 | 95 | 0 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Hardware | 1.000 | 0.500 | 0.667 | 1 | 1 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.579 | 1.000 | 0.733 | 33 | 57 | 33 |
| Organization | 0.580 | 0.976 | 0.727 | 40 | 69 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 27 | 0 |
| Ship | 0.844 | 0.675 | 0.750 | 27 | 32 | 40 |
| Software | 0.500 | 0.250 | 0.333 | 1 | 2 | 4 |
| Source | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 11 | 0 |
| Technology | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vehicle | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Organization: 6
- Ship -> Person: 6
- Software -> TTP: 3
- Ship -> Location: 1
- Document -> Event: 1
- Hardware -> Software: 1

## Relationships

Predicted types: ASSOCIATED_WITH 152, OCCURRED_ON 46, LOCATED_AT 35, MENTIONED_IN 35, TARGETS 22, USES 13, DEPLOYED_AT 11, BELONGS_TO 7, COMMUNICATES_WITH 5, ATTRIBUTED_TO 4, EXPLOITS 2, ASSESSES 1, RESOLVES_TO 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 1 | 1 |
| EXPLOITS | 1 | 1 |
| LOCATED_AT | 6 | 10 |
| TARGETS | 4 | 5 |
| USES | 4 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 269, retired 44, dropped 19 {'ASSOCIATED_WITH': 15, 'MENTIONED_IN': 2, 'BELONGS_TO': 1, 'USES': 1}; entities created 329, filtered 0, dates orphaned 44.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date]
- extra: CISA-NSA joint advisory [Event], Guam telecommunications providers [Organization], Volt Typhoon targeting Guam telecommunications providers [Attack]
- edges: CISA -ASSOCIATED_WITH-> CISA-NSA joint advisory; CISA-NSA joint advisory -OCCURRED_ON-> 24 May 2023; Microsoft -ASSOCIATED_WITH-> Volt Typhoon; NSA -ASSOCIATED_WITH-> CISA-NSA joint advisory; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -COMMUNICATES_WITH-> 185.220.101.42; Volt Typhoon -COMMUNICATES_WITH-> evil-c2.com; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -OCCURRED_ON-> Guam telecommunications providers; Volt Typhoon -TARGETS-> Guam telecommunications providers; Volt Typhoon targeting Guam telecommunications providers -OCCURRED_ON-> 24 May 2023
- gold edges missed: none
- build: created 9, dropped 0 {}

### volt_typhoon_2

- mistyped: CISA Advisory AA23-144a: Document -> Event, Fortinet FortiGuard: Hardware -> Software, netsh: Software -> TTP, ntdsutil: Software -> TTP, wmic: Software -> TTP
- missed: CISA [Organization]
- extra: Compromise of critical infrastructure networks [Event]
- edges: CISA Advisory AA23-144a -MENTIONED_IN-> Compromise of critical infrastructure networks; Compromise of critical infrastructure networks -ATTRIBUTED_TO-> Volt Typhoon; Compromise of critical infrastructure networks -TARGETS-> Guam; Compromise of critical infrastructure networks -TARGETS-> United States; Fortinet FortiGuard -TARGETS-> CVE-2023-27997; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> ASUS; Volt Typhoon -USES-> Cisco; Volt Typhoon -USES-> Netgear; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 15, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: Volt Typhoon campaign [Campaign], earlier intrusions against Naval Base Guam [Event]
- edges: Microsoft -ASSOCIATED_WITH-> Volt Typhoon campaign; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE router -COMMUNICATES_WITH-> Volt Typhoon; Netgear ProSAFE router -RESOLVES_TO-> 45.83.12.7; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -LOCATED_AT-> Guam; Volt Typhoon -USES-> Windows; Volt Typhoon campaign -ASSOCIATED_WITH-> earlier intrusions against Naval Base Guam; Volt Typhoon campaign -TARGETS-> Asia; Volt Typhoon campaign -TARGETS-> United States; earlier intrusions against Naval Base Guam -TARGETS-> Naval Base Guam
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 12, dropped 0 {}

## Corpus: most frequent misses and extras

Missed: none.

Extra: Source [Person] x6, Quay 4 [Location] x4, Imagery Analyst [Person] x3, Partner [Organization] x3, 3 affected sailings [Event] x3, publicised national exercise [Event] x3, Valdorian naval liaison [Person] x3, Imagery collection of Torvik [Event] x2, reporting [Event] x2, Quay 5 [Location] x2, Apron [Location] x2, apron [Location] x2, Liaison reporting [Event] x2, Quay 1 [Location] x2, Collection against Meran Strait [Event] x2.
