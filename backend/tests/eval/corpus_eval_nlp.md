# Corpus extraction eval — `nlp`

Generated 2026-10-02T01:10:18+00:00 at `26704091`; spaCy `en_core_web_sm`.

No document degraded: every score below is the requested mode's own.

Relationships are scored twice. **typed** leaves out generic associations (`ASSOCIATED_WITH`) and date links (`OCCURRED_ON`, or any edge with a Date endpoint), which the gold does not label; **all** scores every edge.

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel typed P / R / F1 | Typed TP / Pred / Gold | Rel all P / R / F1 | All TP / Pred / Gold |
|---|---|---|---|---|---|---|---|---|
| openrep | 40 | 0.674 / 0.949 / 0.788 | 0.728 | 0.924 | 0.649 / 0.507 / 0.569 | 37 / 57 / 73 | 0.060 / 0.507 / 0.107 | 37 / 617 / 73 |
| kestrel | 40 | 0.896 / 0.925 / 0.910 | 0.656 | 0.721 | 1.000 / 0.200 / 0.333 | 2 / 2 / 10 | 0.040 / 0.200 / 0.067 | 2 / 50 / 10 |
| cyber | 3 | 1.000 / 0.923 / 0.960 | 0.960 | 1.000 | 1.000 / 0.615 / 0.762 | 8 / 8 / 13 | 0.210 / 0.615 / 0.314 | 8 / 38 / 13 |
| **combined** | 83 | 0.713 / 0.944 / 0.812 | 0.731 | 0.899 | 0.702 / 0.490 / 0.577 | 47 / 67 / 96 | 0.067 / 0.490 / 0.117 | 47 / 705 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.713 | 0.944 | 0.812 | 606 | 850 | 642 |
| Entities (name + type) | 0.641 | 0.849 | 0.731 | 545 | 850 | 642 |
| Relationships (typed) | 0.702 | 0.490 | 0.577 | 47 | 67 | 96 |
| Relationships (all) | 0.067 | 0.490 | 0.117 | 47 | 705 | 96 |

Type accuracy on matched entities: **0.899** (parent category: 0.901). Gold relationship pairs connected by any edge: 77 of 96. Predicted edges: 67 typed, 635 generic, 3 date links (ASSOCIATED_WITH share 90.1%). Dropped by the extraction: same_entity 7.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Date | 0.649 | 0.984 | 0.782 | 124 | 191 | 126 |
| Document | 0.742 | 0.676 | 0.708 | 23 | 31 | 34 |
| Domain | 0.500 | 1.000 | 0.667 | 1 | 2 | 1 |
| Drone | 0.000 | 0.000 | 0.000 | 0 | 0 | 1 |
| Event | 0.750 | 0.250 | 0.375 | 3 | 4 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 15 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.880 | 0.876 | 0.878 | 162 | 184 | 185 |
| Organization | 0.512 | 0.867 | 0.644 | 150 | 293 | 173 |
| Person | 0.456 | 0.912 | 0.608 | 31 | 68 | 34 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Quantity | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Ship | 0.941 | 0.640 | 0.762 | 32 | 34 | 50 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| Technology | 0.000 | 0.000 | 0.000 | 0 | 0 | 3 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Weapon | 0.857 | 0.600 | 0.706 | 6 | 7 | 10 |

## Type confusion (gold -> predicted)

- Location -> Organization: 15
- Ship -> Person: 13
- Event -> Organization: 5
- Organization -> Person: 4
- Location -> Person: 3
- Document -> Organization: 3
- Event -> Location: 3
- Document -> Location: 2
- Weapon -> Organization: 2
- Ship -> Location: 1
- Organization -> Location: 1
- Drone -> Weapon: 1
- Person -> Organization: 1
- Organization -> Domain: 1
- Document -> Date: 1
- Technology -> Organization: 1
- Technology -> Location: 1
- Organization -> Document: 1
- Person -> Location: 1
- Ship -> Product: 1

## Relationships

Predicted types: ASSOCIATED_WITH 635, BELONGS_TO 30, TARGETS 13, SUPPLIED_BY 8, USES 7, COMMANDED_BY 3, OCCURRED_ON 3, DEPLOYED_AT 2, ATTRIBUTED_TO 1, EXPLOITS 1, LOCATED_AT 1, FUNDED_BY 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 1 | 2 |
| BELONGS_TO | 21 | 36 |
| COMMANDED_BY | 2 | 3 |
| DEPLOYED_AT | 1 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 1 | 1 |
| LOCATED_AT | 1 | 13 |
| SUPPLIED_BY | 4 | 5 |
| TARGETS | 10 | 23 |
| USES | 5 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 67, retired 3, dropped 635 {'ASSOCIATED_WITH': 635} {'below_cooccurrence_min': 635, 'unknown_endpoint': 0}; entities created 642, filtered 0, dates orphaned 190.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: 185.220.101.42 -ASSOCIATED_WITH-> evil-c2.com; China -ASSOCIATED_WITH-> Guam; Fortinet -ASSOCIATED_WITH-> CVE-2023-27997; Microsoft -ASSOCIATED_WITH-> CVE-2023-27997; Microsoft -ASSOCIATED_WITH-> Fortinet; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam
- gold edges missed: none
- build: created 3, dropped 5 {'ASSOCIATED_WITH': 5}

### volt_typhoon_2

- mistyped: none
- missed: AA23-144a [Document], CISA [Organization]
- extra: none
- edges: ASUS -ASSOCIATED_WITH-> Cisco; ASUS -ASSOCIATED_WITH-> Netgear; Cisco -ASSOCIATED_WITH-> Netgear; Fortinet FortiGuard -ASSOCIATED_WITH-> CVE-2023-27997; Guam -ASSOCIATED_WITH-> United States; People's Republic of China -ASSOCIATED_WITH-> Guam; People's Republic of China -ASSOCIATED_WITH-> Volt Typhoon; Volt Typhoon -ASSOCIATED_WITH-> United States; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic; netsh -ASSOCIATED_WITH-> ntdsutil; netsh -ASSOCIATED_WITH-> wmic; ntdsutil -ASSOCIATED_WITH-> wmic
- gold edges missed: Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> United States
- build: created 4, dropped 11 {'ASSOCIATED_WITH': 11}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: none
- edges: Guam -ASSOCIATED_WITH-> Asia; Guam -ASSOCIATED_WITH-> United States; Kaohsiung -ASSOCIATED_WITH-> Manila; Kaohsiung -ASSOCIATED_WITH-> Taiwan; Microsoft -ASSOCIATED_WITH-> Naval Base Guam; NSA -ASSOCIATED_WITH-> Guam; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE -ASSOCIATED_WITH-> 45.83.12.7; Taiwan -ASSOCIATED_WITH-> Manila; United States -ASSOCIATED_WITH-> Asia; Volt Typhoon -ASSOCIATED_WITH-> Guam; Volt Typhoon -ASSOCIATED_WITH-> United States; Volt Typhoon -USES-> Windows; Windows -ASSOCIATED_WITH-> Kaohsiung; Windows -ASSOCIATED_WITH-> Taiwan
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 1, dropped 14 {'ASSOCIATED_WITH': 14}

## openrep: most frequent misses, extras and mistypes

Missed: GCHQ [Organization] x1, H.R. 8610 [Document] x1, National Defense Strategy [Document] x1, United States [Location] x1, Allied Maritime Analysis Cell [Organization] x1, Partner Programmes Cell [Organization] x1, Takaichi [Person] x1, E3 [Organization] x1, SIG-OAR [Organization] x1, Resolution 2758 [Document] x1, CFIUS [Organization] x1, WeChat [Organization] x1, Houthis [Organization] x1, Shahab-3 [Weapon] x1, Donetsk [Location] x1.

Extra: Trump Administration [Organization] x5, 2026 [Date] x4, CRS [Organization] x4, National Security [Organization] x3, 2023 [Date] x3, 2018 [Date] x2, Department [Organization] x2, Strait [Location] x2, 2019 [Date] x2, 2020 [Date] x2, 2025 [Date] x2, State [Organization] x2, 2015 [Date] x2, UN [Organization] x2, Department of War [Organization] x2.

Mistyped (gold -> predicted): Location -> Organization x6, Event -> Organization x5, Organization -> Person x4, Document -> Organization x3, Event -> Location x3, Location -> Person x2, Document -> Location x2, Weapon -> Organization x2, Organization -> Location x1, Drone -> Weapon x1.

## kestrel: most frequent misses, extras and mistypes

Missed: 19th Signals Regiment [Organization] x3, 7th Composite Aviation Detachment [Organization] x3, 15-18 August [Date] x1.

Extra: Comparison [Organization] x3, Liaison [Person] x2, E03 [Organization] x1, approximately 20 per cent [Financial] x1, approximately 10 per cent [Financial] x1, approximately 30 per cent [Financial] x1, some 600 metres [Quantity] x1.

Mistyped (gold -> predicted): Ship -> Person x13, Location -> Organization x9, Ship -> Location x1, Location -> Person x1.
