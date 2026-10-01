# Corpus extraction eval — `hybrid`

Generated 2026-10-01T04:31:25+00:00 at `85559543`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (0 live replies, 86 replayed).

**1 document(s) degraded to NLP** — their numbers are NLP numbers:

- openrep/crs-R44175_10: reply had no entities or relationships list

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel P / R / F1 | Rel TP / Pred / Gold |
|---|---|---|---|---|---|---|
| openrep | 40 | 0.548 / 0.925 / 0.688 | 0.628 | 0.913 | 0.033 / 0.343 / 0.061 | 25 / 749 / 73 |
| kestrel | 40 | 0.756 / 1.000 / 0.861 | 0.768 | 0.892 | 0.051 / 0.400 / 0.091 | 4 / 78 / 10 |
| cyber | 3 | 0.949 / 0.949 / 0.949 | 0.949 | 1.000 | 0.333 / 0.846 / 0.478 | 11 / 33 / 13 |
| **combined** | 83 | 0.588 / 0.938 / 0.723 | 0.661 | 0.915 | 0.046 / 0.417 / 0.084 | 40 / 860 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.588 | 0.938 | 0.723 | 602 | 1024 | 642 |
| Entities (name + type) | 0.538 | 0.858 | 0.661 | 551 | 1024 | 642 |
| Relationships | 0.046 | 0.417 | 0.084 | 40 | 860 | 96 |

Type accuracy on matched entities: **0.915** (parent category: 0.915). Gold relationship pairs connected by any edge: 64 of 96. ASSOCIATED_WITH share of predicted edges: 34.8%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Activity | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 13 | 0 |
| Concept | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Date | 0.707 | 0.921 | 0.800 | 116 | 164 | 126 |
| Document | 0.324 | 0.706 | 0.444 | 24 | 74 | 34 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Drone | 0.333 | 1.000 | 0.500 | 1 | 3 | 1 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 16 | 0 |
| Event | 0.098 | 0.667 | 0.170 | 8 | 82 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 6 | 0 |
| Hardware | 0.667 | 1.000 | 0.800 | 2 | 3 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Indicator | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Infrastructure | 0.000 | 0.000 | 0.000 | 0 | 4 | 0 |
| Location | 0.754 | 0.860 | 0.803 | 159 | 211 | 185 |
| Material | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Organization | 0.603 | 0.913 | 0.726 | 158 | 262 | 173 |
| Person | 0.620 | 0.912 | 0.738 | 31 | 50 | 34 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 27 | 0 |
| Program | 0.000 | 0.000 | 0.000 | 0 | 10 | 0 |
| Ship | 0.912 | 0.620 | 0.738 | 31 | 34 | 50 |
| Software | 0.500 | 1.000 | 0.667 | 4 | 8 | 4 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 11 | 0 |
| Technology | 0.167 | 0.333 | 0.222 | 1 | 6 | 3 |
| ThreatActor | 0.429 | 1.000 | 0.600 | 3 | 7 | 3 |
| Treaty | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Weapon | 0.615 | 0.800 | 0.696 | 8 | 13 | 10 |

## Type confusion (gold -> predicted)

- Location -> Organization: 13
- Ship -> Person: 7
- Ship -> Equipment: 7
- Ship -> Location: 4
- Location -> ThreatActor: 3
- Organization -> Software: 3
- Event -> Campaign: 2
- Weapon -> Organization: 2
- Organization -> ThreatActor: 1
- Location -> TTP: 1
- Date -> Organization: 1
- Ship -> Organization: 1
- Technology -> Campaign: 1
- Person -> Organization: 1
- Document -> Treaty: 1
- Person -> Location: 1
- Organization -> Event: 1
- Location -> Event: 1

## Relationships

Predicted types: ASSOCIATED_WITH 299, TARGETS 139, OCCURRED_ON 125, USES 67, BELONGS_TO 60, LOCATED_AT 44, SUPPLIED_BY 43, MENTIONED_IN 27, DEPLOYED_AT 19, ATTRIBUTED_TO 12, COMMUNICATES_WITH 8, FUNDED_BY 5, COMMANDED_BY 3, EXPLOITS 2, ASSESSES 2, SUPPORTED_BY 2, RELATED_TO 2, RESOLVES_TO 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 2 | 2 |
| BELONGS_TO | 12 | 36 |
| COMMANDED_BY | 0 | 3 |
| DEPLOYED_AT | 2 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 0 | 1 |
| LOCATED_AT | 4 | 13 |
| SUPPLIED_BY | 0 | 5 |
| TARGETS | 15 | 23 |
| USES | 4 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 652, retired 112, dropped 71 {'ASSOCIATED_WITH': 42, 'TARGETS': 14, 'USES': 4, 'LOCATED_AT': 4, 'MENTIONED_IN': 3, 'OCCURRED_ON': 2, 'DEPLOYED_AT': 1, 'BELONGS_TO': 1}; entities created 844, filtered 1, dates orphaned 116.

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
- edges: Kaohsiung -LOCATED_AT-> Taiwan; Microsoft -ASSOCIATED_WITH-> Volt Typhoon; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE router -RESOLVES_TO-> 45.83.12.7; Netgear ProSAFE router -USES-> Volt Typhoon; Volt Typhoon -ASSOCIATED_WITH-> Naval Base Guam; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -LOCATED_AT-> Guam networks; Volt Typhoon -TARGETS-> Asia; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> Windows; Volt Typhoon -USES-> built-in Windows tools
- gold edges missed: Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 12, dropped 1 {'USES': 1}

## openrep: most frequent misses, extras and mistypes

Missed: 2023 [Date] x2, Middle East [Location] x2, E.O. 14186 [Document] x2, E.O. 14347 [Document] x2, European Commission [Organization] x1, Poland [Location] x1, 1992 [Date] x1, Africa Initiative [Organization] x1, Africa Summit [Event] x1, Alliance of Sahel States [Organization] x1, Niger [Location] x1, Nordgold [Organization] x1, Ouagadougou [Location] x1, Traoré [Person] x1, Wagner Group [Organization] x1.

Extra: U.S. [Location] x4, Trump Administration [Organization] x4, DOD [Organization] x3, Tehran [Location] x3, 2023 [Date] x3, Navy [Organization] x3, China [Location] x3, Baltic [Location] x2, Hybrid warfare [Campaign] x2, 2018 [Date] x2, Department [Organization] x2, Russian intelligence services [Organization] x2, 2026 [Date] x2, IAEA [Organization] x2, Israel [Organization] x2.

Mistyped (gold -> predicted): Location -> Organization x13, Ship -> Equipment x7, Location -> ThreatActor x3, Organization -> Software x3, Event -> Campaign x2, Weapon -> Organization x2, Organization -> ThreatActor x1, Location -> TTP x1, Date -> Organization x1, Ship -> Organization x1.

## kestrel: most frequent misses, extras and mistypes

Missed: none.

Extra: Valdorian [Location] x2, EXERCISE — FICTIONAL [Event] x1, Quay 4 [Location] x1, Comparison against imagery of 3 days earlier [Event] x1, Imagery establishes presence and disposition [Event] x1, Imagery of Torvik collected during the period [Event] x1, Observed dispersal pattern [Event] x1, EXERCISE — FICTIONAL [Document] x1, Collection at 1742Z [Event] x1, E03 [Document] x1, Loading activity [Event] x1, Sedne fuel uptake [Event] x1, apron [Location] x1, naval jetty [Location] x1, Escort tasking assignment [Event] x1.

Mistyped (gold -> predicted): Ship -> Person x7, Ship -> Location x3.
