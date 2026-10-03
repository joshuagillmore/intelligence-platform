# Corpus extraction eval — `llm`

Generated 2026-10-02T12:36:02+00:00 at `9e862798`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (0 live replies, 83 replayed).

No document degraded: every score below is the requested mode's own.

Relationships are scored twice. **typed** leaves out generic associations (`ASSOCIATED_WITH`) and date links (`OCCURRED_ON`, or any edge with a Date endpoint), which the gold does not label; **all** scores every edge.

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel typed P / R / F1 | Typed TP / Pred / Gold | Rel all P / R / F1 | All TP / Pred / Gold |
|---|---|---|---|---|---|---|---|---|
| openrep | 40 | 0.611 / 0.925 / 0.736 | 0.692 | 0.941 | 0.140 / 0.384 / 0.205 | 28 / 200 / 73 | 0.063 / 0.384 / 0.108 | 28 / 443 / 73 |
| kestrel | 40 | 0.816 / 1.000 / 0.899 | 0.831 | 0.925 | 0.389 / 0.700 / 0.500 | 7 / 18 / 10 | 0.159 / 0.700 / 0.259 | 7 / 44 / 10 |
| cyber | 3 | 0.897 / 0.897 / 0.897 | 0.897 | 1.000 | 0.500 / 0.615 / 0.552 | 8 / 16 / 13 | 0.471 / 0.615 / 0.533 | 8 / 17 / 13 |
| **combined** | 83 | 0.648 / 0.935 / 0.765 | 0.721 | 0.942 | 0.184 / 0.448 / 0.261 | 43 / 234 / 96 | 0.085 / 0.448 / 0.143 | 43 / 504 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.648 | 0.935 | 0.765 | 600 | 926 | 642 |
| Entities (name + type) | 0.610 | 0.880 | 0.721 | 565 | 926 | 642 |
| Relationships (typed) | 0.184 | 0.448 | 0.261 | 43 | 234 | 96 |
| Relationships (all) | 0.085 | 0.448 | 0.143 | 43 | 504 | 96 |

Type accuracy on matched entities: **0.942** (parent category: 0.942). Gold relationship pairs connected by any edge: 58 of 96. Predicted edges: 234 typed, 182 generic, 88 date links (ASSOCIATED_WITH share 36.1%). Dropped by the extraction: evidence_missing_endpoint 180, evidence_not_verbatim 119, generic_on_typed_pair 7, repeated 110, same_entity 5, unlisted_endpoint 44. Evidence spans: 504 located at their offset, 0 without one, 0 mismatched.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 11 | 0 |
| Commodity | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Currency | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Date | 0.764 | 0.873 | 0.815 | 110 | 144 | 126 |
| Document | 0.388 | 0.765 | 0.515 | 26 | 67 | 34 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Drone | 0.333 | 1.000 | 0.500 | 1 | 3 | 1 |
| Economic | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Event | 0.120 | 0.917 | 0.211 | 11 | 92 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Fund | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Infrastructure | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Location | 0.832 | 0.908 | 0.868 | 168 | 202 | 185 |
| Organization | 0.714 | 0.907 | 0.799 | 157 | 220 | 173 |
| Person | 0.702 | 0.971 | 0.815 | 33 | 47 | 34 |
| Policy | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Project | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Sector | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Service | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Ship | 0.861 | 0.740 | 0.796 | 37 | 43 | 50 |
| Software | 0.375 | 0.750 | 0.500 | 3 | 8 | 4 |
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
- Date -> Event: 3
- Ship -> Person: 2
- Date -> Document: 2
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

Predicted types: ASSOCIATED_WITH 182, OCCURRED_ON 88, TARGETS 64, BELONGS_TO 56, USES 30, LOCATED_AT 27, SUPPLIED_BY 22, DEPLOYED_AT 14, ATTRIBUTED_TO 5, MENTIONED_IN 5, COMMUNICATES_WITH 4, EXPLOITS 3, COMMANDED_BY 3, FUNDED_BY 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 12 | 36 |
| COMMANDED_BY | 1 | 3 |
| DEPLOYED_AT | 2 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 0 | 1 |
| LOCATED_AT | 7 | 13 |
| SUPPLIED_BY | 0 | 5 |
| TARGETS | 15 | 23 |
| USES | 3 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 404, retired 88, dropped 12 {'ASSOCIATED_WITH': 12} {'below_cooccurrence_min': 0, 'unknown_endpoint': 12}; entities created 769, filtered 0, dates orphaned 112.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date], Guam [Location]
- extra: CISA-NSA joint advisory [Event], living-off-the-land [TTP]
- edges: CISA-NSA joint advisory -OCCURRED_ON-> 24 May 2023; Fortinet -TARGETS-> CVE-2023-27997; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -USES-> living-off-the-land
- gold edges missed: Volt Typhoon -TARGETS-> Guam
- build: created 4, dropped 0 {}

### volt_typhoon_2

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: Fortinet FortiGuard -EXPLOITS-> CVE-2023-27997; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 7, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: Windows [Software]
- extra: Volt Typhoon pre-positioning campaign [Event], earlier intrusions against Naval Base Guam [Event]
- edges: Netgear ProSAFE router -LOCATED_AT-> 45.83.12.7; Volt Typhoon -ATTRIBUTED_TO-> NSA; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; earlier intrusions against Naval Base Guam -TARGETS-> Naval Base Guam
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam; Volt Typhoon -USES-> Windows
- build: created 5, dropped 0 {}

## openrep: most frequent misses, extras and mistypes

Missed: 2022 [Date] x3, United States [Location] x3, Congress [Organization] x3, Europe [Location] x2, U.S. Space Force [Organization] x2, European Commission [Organization] x1, Ukraine [Location] x1, Eurasia [Location] x1, Taiwan Strait [Location] x1, February 28 [Date] x1, Beijing [Location] x1, 2017 [Date] x1, March 2018 [Date] x1, August 2020 [Date] x1, Asia [Location] x1.

Extra: U.S. [Location] x6, Trump Administration [Organization] x5, Israel [Location] x3, United States [Location] x3, U.S.-Israeli airstrikes [Event] x2, P.L. 119-60 [Document] x2, CRS [Organization] x2, Navy Office of Legislative Affairs [Organization] x2, 2021 [Date] x2, OPENREP-SUPINTREP-0004 [Event] x1, crs-IF11797 [Event] x1, crs-IN12602 [Event] x1, crs-R48978 [Event] x1, Baltic region [Location] x1, OPENREP-SUPINTREP-0006 [Document] x1.

Mistyped (gold -> predicted): Document -> Event x4, Organization -> Software x4, Location -> Organization x3, Date -> Event x3, Date -> Document x2, Weapon -> System x2, Ship -> Organization x1, Technology -> Campaign x1, Person -> Organization x1, Organization -> Event x1.

## kestrel: most frequent misses, extras and mistypes

Missed: none.

Extra: Valdorian [Location] x2, quay 4 [Location] x1, E03 [Document] x1, NIIRS [System] x1, GNSS [Technology] x1, central strait [Location] x1, Ravenskan [Ship] x1, Ravenskan hydrographic survey transit [Event] x1, callsign activity [Event] x1, interference cessation [Event] x1, AIS [Technology] x1, Synthetic aperture imagery [Technology] x1, transponder failure [Event] x1, publicised national exercise [Event] x1, Voice communications jamming incident [Event] x1.

Mistyped (gold -> predicted): Ship -> Organization x4, Ship -> Person x2, Ship -> Location x1.
