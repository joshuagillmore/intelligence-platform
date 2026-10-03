# Corpus extraction eval — `hybrid`

Generated 2026-10-02T12:36:20+00:00 at `9e862798`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (0 live replies, 83 replayed).

No document degraded: every score below is the requested mode's own.

Relationships are scored twice. **typed** leaves out generic associations (`ASSOCIATED_WITH`) and date links (`OCCURRED_ON`, or any edge with a Date endpoint), which the gold does not label; **all** scores every edge.

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel typed P / R / F1 | Typed TP / Pred / Gold | Rel all P / R / F1 | All TP / Pred / Gold |
|---|---|---|---|---|---|---|---|---|
| openrep | 40 | 0.585 / 0.961 / 0.727 | 0.693 | 0.953 | 0.213 / 0.712 / 0.328 | 52 / 244 / 73 | 0.107 / 0.712 / 0.186 | 52 / 485 / 73 |
| kestrel | 40 | 0.809 / 1.000 / 0.894 | 0.827 | 0.925 | 0.389 / 0.700 / 0.500 | 7 / 18 / 10 | 0.159 / 0.700 / 0.259 | 7 / 44 / 10 |
| cyber | 3 | 0.902 / 0.949 / 0.925 | 0.925 | 1.000 | 0.556 / 0.769 / 0.645 | 10 / 18 / 13 | 0.526 / 0.769 / 0.625 | 10 / 19 / 13 |
| **combined** | 83 | 0.624 / 0.966 / 0.758 | 0.721 | 0.952 | 0.246 / 0.719 / 0.367 | 69 / 280 / 96 | 0.126 / 0.719 / 0.214 | 69 / 548 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.624 | 0.966 | 0.758 | 620 | 994 | 642 |
| Entities (name + type) | 0.594 | 0.919 | 0.721 | 590 | 994 | 642 |
| Relationships (typed) | 0.246 | 0.719 | 0.367 | 69 | 280 | 96 |
| Relationships (all) | 0.126 | 0.719 | 0.214 | 69 | 548 | 96 |

Type accuracy on matched entities: **0.952** (parent category: 0.952). Gold relationship pairs connected by any edge: 76 of 96. Predicted edges: 280 typed, 178 generic, 90 date links (ASSOCIATED_WITH share 32.5%). Dropped by the extraction: evidence_missing_endpoint 180, evidence_not_verbatim 119, generic_on_typed_pair 11, repeated 115, same_entity 5, unlisted_endpoint 36. Evidence spans: 548 located at their offset, 0 without one, 0 mismatched.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 11 | 0 |
| Commodity | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Currency | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Date | 0.739 | 0.944 | 0.829 | 119 | 161 | 126 |
| Document | 0.397 | 0.794 | 0.529 | 27 | 68 | 34 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Drone | 0.333 | 1.000 | 0.500 | 1 | 3 | 1 |
| Economic | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Event | 0.120 | 0.917 | 0.211 | 11 | 92 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Fund | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Infrastructure | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Location | 0.807 | 0.930 | 0.864 | 172 | 213 | 185 |
| Organization | 0.659 | 0.948 | 0.777 | 164 | 249 | 173 |
| Person | 0.660 | 0.971 | 0.786 | 33 | 50 | 34 |
| Policy | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Project | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Sector | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Service | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Ship | 0.870 | 0.800 | 0.833 | 40 | 46 | 50 |
| Software | 0.444 | 1.000 | 0.615 | 4 | 9 | 4 |
| System | 0.000 | 0.000 | 0.000 | 0 | 9 | 0 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Technology | 0.143 | 0.333 | 0.200 | 1 | 7 | 3 |
| ThreatActor | 0.750 | 1.000 | 0.857 | 3 | 4 | 3 |
| Treaty | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Weapon | 0.533 | 0.800 | 0.640 | 8 | 15 | 10 |

## Type confusion (gold -> predicted)

- Ship -> Organization: 5
- Organization -> Software: 4
- Document -> Event: 4
- Location -> Organization: 3
- Ship -> Person: 2
- Weapon -> System: 2
- Ship -> Location: 1
- Technology -> Campaign: 1
- Person -> Organization: 1
- Document -> Organization: 1
- Organization -> Event: 1
- Document -> Treaty: 1
- Document -> Campaign: 1
- Technology -> Organization: 1
- Ship -> Equipment: 1
- Location -> Event: 1

## Relationships

Predicted types: ASSOCIATED_WITH 178, OCCURRED_ON 90, BELONGS_TO 77, TARGETS 70, USES 34, SUPPLIED_BY 31, LOCATED_AT 27, DEPLOYED_AT 16, COMMANDED_BY 6, ATTRIBUTED_TO 5, MENTIONED_IN 5, COMMUNICATES_WITH 4, EXPLOITS 3, FUNDED_BY 2.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 25 | 36 |
| COMMANDED_BY | 3 | 3 |
| DEPLOYED_AT | 3 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 1 | 1 |
| LOCATED_AT | 7 | 13 |
| SUPPLIED_BY | 4 | 5 |
| TARGETS | 18 | 23 |
| USES | 5 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 446, retired 90, dropped 12 {'ASSOCIATED_WITH': 12} {'below_cooccurrence_min': 0, 'unknown_endpoint': 12}; entities created 818, filtered 0, dates orphaned 128.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date]
- extra: CISA-NSA joint advisory [Event], living-off-the-land [TTP]
- edges: CISA-NSA joint advisory -OCCURRED_ON-> 24 May 2023; Fortinet -TARGETS-> CVE-2023-27997; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -USES-> living-off-the-land
- gold edges missed: none
- build: created 5, dropped 0 {}

### volt_typhoon_2

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: Fortinet FortiGuard -EXPLOITS-> CVE-2023-27997; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 7, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: Volt Typhoon pre-positioning campaign [Event], earlier intrusions against Naval Base Guam [Event]
- edges: Netgear ProSAFE router -LOCATED_AT-> 45.83.12.7; Volt Typhoon -ATTRIBUTED_TO-> NSA; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -USES-> Windows; earlier intrusions against Naval Base Guam -TARGETS-> Naval Base Guam
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 6, dropped 0 {}

## openrep: most frequent misses, extras and mistypes

Missed: United States [Location] x3, Europe [Location] x2, 2022 [Date] x2, Eurasia [Location] x1, Taiwan Strait [Location] x1, February 28 [Date] x1, 2017 [Date] x1, Asia [Location] x1, 2006 [Date] x1, 2015 [Date] x1, Lebanon [Location] x1, Congress [Organization] x1, DHS [Organization] x1, LSD [Ship] x1, EU [Organization] x1.

Extra: U.S. [Location] x6, Trump Administration [Organization] x5, Israel [Location] x3, 2023 [Date] x3, United States [Location] x3, Baltic [Location] x2, Department [Organization] x2, 2026 [Date] x2, U.S.-Israeli airstrikes [Event] x2, Strait [Location] x2, P.L. 119-60 [Document] x2, SLTT [Organization] x2, CRS [Organization] x2, Navy Office of Legislative Affairs [Organization] x2, 2021 [Date] x2.

Mistyped (gold -> predicted): Document -> Event x4, Organization -> Software x4, Location -> Organization x3, Weapon -> System x2, Ship -> Organization x1, Technology -> Campaign x1, Person -> Organization x1, Organization -> Event x1, Document -> Organization x1, Document -> Treaty x1.

## kestrel: most frequent misses, extras and mistypes

Missed: none.

Extra: Valdorian [Location] x2, quay 4 [Location] x1, E03 [Document] x1, NIIRS [System] x1, GNSS [Technology] x1, central strait [Location] x1, Ravenskan [Ship] x1, Ravenskan hydrographic survey transit [Event] x1, callsign activity [Event] x1, interference cessation [Event] x1, AIS [Technology] x1, Synthetic aperture imagery [Technology] x1, transponder failure [Event] x1, Air Defence Battalion [Organization] x1, publicised national exercise [Event] x1.

Mistyped (gold -> predicted): Ship -> Organization x4, Ship -> Person x2, Ship -> Location x1.
