# Corpus extraction eval — `llm`

Generated 2026-10-02T01:10:25+00:00 at `26704091`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (0 live replies, 83 replayed).

No document degraded: every score below is the requested mode's own.

Relationships are scored twice. **typed** leaves out generic associations (`ASSOCIATED_WITH`) and date links (`OCCURRED_ON`, or any edge with a Date endpoint), which the gold does not label; **all** scores every edge.

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel typed P / R / F1 | Typed TP / Pred / Gold | Rel all P / R / F1 | All TP / Pred / Gold |
|---|---|---|---|---|---|---|---|---|
| openrep | 40 | 0.632 / 0.949 / 0.759 | 0.707 | 0.932 | 0.091 / 0.397 / 0.149 | 29 / 317 / 73 | 0.044 / 0.397 / 0.080 | 29 / 652 / 73 |
| kestrel | 40 | 0.802 / 1.000 / 0.890 | 0.823 | 0.925 | 0.316 / 0.600 / 0.414 | 6 / 19 / 10 | 0.143 / 0.600 / 0.231 | 6 / 42 / 10 |
| cyber | 3 | 0.974 / 0.949 / 0.961 | 0.961 | 1.000 | 0.458 / 0.846 / 0.595 | 11 / 24 / 13 | 0.393 / 0.846 / 0.537 | 11 / 28 / 13 |
| **combined** | 83 | 0.667 / 0.956 / 0.786 | 0.735 | 0.935 | 0.128 / 0.479 / 0.202 | 46 / 360 / 96 | 0.064 / 0.479 / 0.113 | 46 / 722 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.667 | 0.956 | 0.786 | 614 | 920 | 642 |
| Entities (name + type) | 0.624 | 0.894 | 0.735 | 574 | 920 | 642 |
| Relationships (typed) | 0.128 | 0.479 | 0.202 | 46 | 360 | 96 |
| Relationships (all) | 0.064 | 0.479 | 0.113 | 46 | 722 | 96 |

Type accuracy on matched entities: **0.935** (parent category: 0.935). Gold relationship pairs connected by any edge: 69 of 96. Predicted edges: 360 typed, 231 generic, 131 date links (ASSOCIATED_WITH share 32.0%). Dropped by the extraction: generic_on_typed_pair 11, same_entity 2, unlisted_endpoint 66.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Agreement | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 8 | 0 |
| Count | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Date | 0.748 | 0.897 | 0.816 | 113 | 151 | 126 |
| Document | 0.324 | 0.676 | 0.438 | 23 | 71 | 34 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Drone | 0.250 | 1.000 | 0.400 | 1 | 4 | 1 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 9 | 0 |
| Event | 0.120 | 0.833 | 0.210 | 10 | 83 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 19 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Infrastructure | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| LegalCitation | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| LegalDocument | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| LegalProvision | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Location | 0.838 | 0.897 | 0.867 | 166 | 198 | 185 |
| Organization | 0.744 | 0.925 | 0.825 | 160 | 215 | 173 |
| Person | 0.791 | 1.000 | 0.883 | 34 | 43 | 34 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 15 | 0 |
| Ship | 0.933 | 0.840 | 0.884 | 42 | 45 | 50 |
| Software | 0.400 | 1.000 | 0.571 | 4 | 10 | 4 |
| System | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Technology | 0.250 | 0.333 | 0.286 | 1 | 4 | 3 |
| Threat | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| ThreatActor | 0.500 | 1.000 | 0.667 | 3 | 6 | 3 |
| Time | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| TimePeriod | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Treaty | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Weapon | 0.769 | 1.000 | 0.870 | 10 | 13 | 10 |

## Type confusion (gold -> predicted)

- Document -> Event: 6
- Ship -> Organization: 4
- Organization -> Software: 4
- Location -> Organization: 3
- Date -> Document: 3
- Ship -> Location: 2
- Ship -> Person: 2
- Organization -> ThreatActor: 2
- Location -> TTP: 1
- Location -> Campaign: 1
- Location -> ThreatActor: 1
- Technology -> Campaign: 1
- Document -> Financial: 1
- Date -> Event: 1
- Document -> Treaty: 1
- Document -> Agreement: 1
- Document -> LegalDocument: 1
- Technology -> Organization: 1
- Event -> Campaign: 1
- Location -> Person: 1
- Organization -> Location: 1
- Location -> Event: 1

## Relationships

Predicted types: ASSOCIATED_WITH 231, OCCURRED_ON 131, TARGETS 103, BELONGS_TO 61, LOCATED_AT 49, USES 42, DEPLOYED_AT 29, SUPPLIED_BY 17, ATTRIBUTED_TO 14, MENTIONED_IN 13, COMMUNICATES_WITH 9, FUNDED_BY 7, EXPLOITS 5, COMMANDED_BY 4, ASSESSES 3, RELATED_TO 2, RESOLVES_TO 1, SUPPORTED_BY 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 11 | 36 |
| COMMANDED_BY | 0 | 3 |
| DEPLOYED_AT | 5 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 0 | 1 |
| LOCATED_AT | 6 | 13 |
| SUPPLIED_BY | 0 | 5 |
| TARGETS | 17 | 23 |
| USES | 4 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 589, retired 130, dropped 3 {'ASSOCIATED_WITH': 3} {'below_cooccurrence_min': 0, 'unknown_endpoint': 3}; entities created 755, filtered 0, dates orphaned 108.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: 2023 [Date]
- extra: joint advisory [Document]
- edges: CISA -ASSOCIATED_WITH-> joint advisory; CVE-2023-27997 -TARGETS-> Fortinet; NSA -ASSOCIATED_WITH-> joint advisory; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -COMMUNICATES_WITH-> 185.220.101.42; Volt Typhoon -COMMUNICATES_WITH-> evil-c2.com; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; joint advisory -OCCURRED_ON-> 24 May 2023
- gold edges missed: none
- build: created 8, dropped 0 {}

### volt_typhoon_2

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: ASUS -SUPPLIED_BY-> Volt Typhoon; CISA Advisory AA23-144a -MENTIONED_IN-> Volt Typhoon; Cisco -SUPPLIED_BY-> Volt Typhoon; Fortinet FortiGuard -ASSOCIATED_WITH-> Volt Typhoon; Fortinet FortiGuard -EXPLOITS-> CVE-2023-27997; Netgear -SUPPLIED_BY-> Volt Typhoon; Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- gold edges missed: none
- build: created 12, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: none
- edges: Microsoft -ATTRIBUTED_TO-> Volt Typhoon; Netgear ProSAFE router -RESOLVES_TO-> 45.83.12.7; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -LOCATED_AT-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam; Volt Typhoon -USES-> Windows
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 7, dropped 0 {}

## openrep: most frequent misses, extras and mistypes

Missed: United States [Location] x3, European Commission [Organization] x1, Poland [Location] x1, Taiwan Strait [Location] x1, 2003 [Date] x1, 2022 [Date] x1, Beijing [Location] x1, 1992 [Date] x1, 2017 [Date] x1, Department of Defense Appropriations Act, 2026 [Document] x1, Asia [Location] x1, Penghu [Location] x1, Seventh Fleet [Organization] x1, UN General Assembly [Organization] x1, 2025 [Date] x1.

Extra: U.S. [Location] x7, Trump Administration [Organization] x6, 2023 [Date] x3, United States [Location] x3, Russian intelligence services [Organization] x2, Israel [Location] x2, U.S.-Israeli airstrikes [Event] x2, CRS [Organization] x2, Navy Office of Legislative Affairs [Organization] x2, 2021 [Date] x2, OPENREP-SUPINTREP-0004 [Document] x1, crs-IF11797 [Document] x1, crs-IN12602 [Document] x1, crs-R48978 [Document] x1, General Alexus G. Grynkewich March 2026 congressional testimony [Event] x1.

Mistyped (gold -> predicted): Document -> Event x6, Organization -> Software x4, Location -> Organization x3, Date -> Document x3, Organization -> ThreatActor x2, Location -> TTP x1, Location -> Campaign x1, Location -> ThreatActor x1, Ship -> Organization x1, Document -> Financial x1.

## kestrel: most frequent misses, extras and mistypes

Missed: none.

Extra: EXERCISE — FICTIONAL [Document] x2, E03 [Document] x1, Cancelled port calls at Torvik [Event] x1, GNSS [Technology] x1, Collection against the Meran Strait [Event] x1, Interference correlation activity [Event] x1, Traffic transmission event [Event] x1, Ravenskan hydrographic survey transit [Event] x1, 0251Z [Time] x1, 2316Z to 0025Z [TimePeriod] x1, 3 affected sailings [Count] x1, AIS [Software] x1, Publicly available shipping and schedule data [Document] x1, Stellar Vane AIS transmission cessation [Event] x1, Partner [Organization] x1.

Mistyped (gold -> predicted): Ship -> Organization x3, Ship -> Location x2, Ship -> Person x2.
