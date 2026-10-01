# Corpus extraction eval — `llm`

Generated 2026-10-01T12:19:09+00:00 at `719b9ca6`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (0 live replies, 83 replayed).

No document degraded: every score below is the requested mode's own.

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel P / R / F1 | Rel TP / Pred / Gold |
|---|---|---|---|---|---|---|
| openrep | 40 | 0.611 / 0.937 / 0.740 | 0.683 | 0.923 | 0.040 / 0.397 / 0.073 | 29 / 722 / 73 |
| kestrel | 40 | 0.762 / 1.000 / 0.865 | 0.772 | 0.892 | 0.051 / 0.400 / 0.091 | 4 / 78 / 10 |
| cyber | 3 | 0.949 / 0.949 / 0.949 | 0.949 | 1.000 | 0.344 / 0.846 / 0.489 | 11 / 32 / 13 |
| **combined** | 83 | 0.645 / 0.947 / 0.767 | 0.708 | 0.923 | 0.053 / 0.458 / 0.095 | 44 / 832 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.645 | 0.947 | 0.767 | 608 | 943 | 642 |
| Entities (name + type) | 0.595 | 0.874 | 0.708 | 561 | 943 | 642 |
| Relationships | 0.053 | 0.458 | 0.095 | 44 | 832 | 96 |

Type accuracy on matched entities: **0.923** (parent category: 0.923). Gold relationship pairs connected by any edge: 69 of 96. ASSOCIATED_WITH share of predicted edges: 33.2%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 13 | 0 |
| Date | 0.728 | 0.849 | 0.784 | 107 | 147 | 126 |
| Document | 0.438 | 0.941 | 0.598 | 32 | 73 | 34 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Drone | 0.333 | 1.000 | 0.500 | 1 | 3 | 1 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 9 | 0 |
| Event | 0.093 | 0.667 | 0.163 | 8 | 86 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Hardware | 0.667 | 1.000 | 0.800 | 2 | 3 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Infrastructure | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Location | 0.800 | 0.843 | 0.821 | 156 | 195 | 185 |
| Organization | 0.684 | 0.925 | 0.786 | 160 | 234 | 173 |
| Person | 0.688 | 0.971 | 0.805 | 33 | 48 | 34 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 25 | 0 |
| Ship | 0.907 | 0.780 | 0.839 | 39 | 43 | 50 |
| Software | 0.500 | 1.000 | 0.667 | 4 | 8 | 4 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 11 | 0 |
| Technology | 0.167 | 0.333 | 0.222 | 1 | 6 | 3 |
| ThreatActor | 0.429 | 1.000 | 0.600 | 3 | 7 | 3 |
| Treaty | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Weapon | 0.667 | 1.000 | 0.800 | 10 | 15 | 10 |

## Type confusion (gold -> predicted)

- Location -> Organization: 14
- Ship -> Person: 7
- Ship -> Location: 3
- Location -> ThreatActor: 3
- Organization -> Software: 3
- Date -> Document: 3
- Event -> Campaign: 2
- Organization -> ThreatActor: 1
- Location -> TTP: 1
- Location -> Campaign: 1
- Date -> Organization: 1
- Technology -> Campaign: 1
- Person -> Organization: 1
- Document -> Treaty: 1
- Organization -> Event: 1
- Location -> Document: 1
- Technology -> Organization: 1
- Ship -> Equipment: 1
- Location -> Event: 1

## Relationships

Predicted types: ASSOCIATED_WITH 276, TARGETS 139, OCCURRED_ON 125, USES 64, BELONGS_TO 60, LOCATED_AT 49, SUPPLIED_BY 38, MENTIONED_IN 25, DEPLOYED_AT 21, ATTRIBUTED_TO 10, COMMUNICATES_WITH 10, COMMANDED_BY 3, FUNDED_BY 3, EXPLOITS 2, ASSESSES 2, SUPPORTED_BY 2, RELATED_TO 2, RESOLVES_TO 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 12 | 36 |
| COMMANDED_BY | 0 | 3 |
| DEPLOYED_AT | 4 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 0 | 1 |
| LOCATED_AT | 5 | 13 |
| SUPPLIED_BY | 0 | 5 |
| TARGETS | 15 | 23 |
| USES | 5 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 649, retired 108, dropped 75 {'ASSOCIATED_WITH': 41, 'TARGETS': 14, 'OCCURRED_ON': 6, 'LOCATED_AT': 5, 'MENTIONED_IN': 3, 'USES': 3, 'DEPLOYED_AT': 2, 'BELONGS_TO': 1}; entities created 783, filtered 0, dates orphaned 100.

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

## openrep: most frequent misses, extras and mistypes

Missed: Middle East [Location] x2, European Commission [Organization] x1, Poland [Location] x1, 2003 [Date] x1, Beijing [Location] x1, Africa Summit [Event] x1, 2017 [Date] x1, March 2018 [Date] x1, Asia [Location] x1, Security Council [Organization] x1, United Nations [Organization] x1, April 2026 [Date] x1, January 2026 [Date] x1, July 2025 [Date] x1, November 2025 [Date] x1.

Extra: U.S. [Location] x5, Trump Administration [Organization] x4, Hybrid warfare [Campaign] x2, 2018 [Date] x2, Russian intelligence services [Organization] x2, Tehran [Location] x2, Israel [Organization] x2, 2023 [Date] x2, U.S. forces [Organization] x2, Department of Defense [Organization] x2, P.L. 119-60 [Document] x2, United States [Location] x2, UAS [Equipment] x2, CRS [Organization] x2, Navy Office of Legislative Affairs [Organization] x2.

Mistyped (gold -> predicted): Location -> Organization x14, Location -> ThreatActor x3, Organization -> Software x3, Date -> Document x3, Event -> Campaign x2, Organization -> ThreatActor x1, Location -> TTP x1, Location -> Campaign x1, Date -> Organization x1, Technology -> Campaign x1.

## kestrel: most frequent misses, extras and mistypes

Missed: none.

Extra: Valdorian [Location] x2, EXERCISE — FICTIONAL [Event] x1, Quay 4 [Location] x1, Comparison against imagery of 3 days earlier [Event] x1, Imagery establishes presence and disposition [Event] x1, Imagery of Torvik collected during the period [Event] x1, Observed dispersal pattern [Event] x1, EXERCISE — FICTIONAL [Document] x1, Collection at 1742Z [Event] x1, E03 [Document] x1, Loading activity [Event] x1, Sedne fuel uptake [Event] x1, apron [Location] x1, naval jetty [Location] x1, Escort tasking assignment [Event] x1.

Mistyped (gold -> predicted): Ship -> Person x7, Ship -> Location x3.
