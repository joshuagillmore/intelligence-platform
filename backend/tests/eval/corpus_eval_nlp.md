# Corpus extraction eval — `nlp`

Generated 2026-10-01T04:18:19+00:00 at `85559543`; spaCy `en_core_web_sm`.

No document degraded: every score below is the requested mode's own.

| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel P / R / F1 | Rel TP / Pred / Gold |
|---|---|---|---|---|---|---|
| openrep | 40 | 0.630 / 0.923 / 0.749 | 0.655 | 0.875 | 0.001 / 0.014 / 0.003 | 1 / 694 / 73 |
| kestrel | 40 | 0.896 / 0.925 / 0.910 | 0.656 | 0.721 | 0.039 / 0.200 / 0.066 | 2 / 51 / 10 |
| cyber | 3 | 1.000 / 0.897 / 0.946 | 0.946 | 1.000 | 0.222 / 0.615 / 0.327 | 8 / 36 / 13 |
| **combined** | 83 | 0.674 / 0.922 / 0.779 | 0.670 | 0.860 | 0.014 / 0.115 / 0.025 | 11 / 781 / 96 |

| Combined metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.674 | 0.922 | 0.779 | 592 | 878 | 642 |
| Entities (name + type) | 0.580 | 0.793 | 0.670 | 509 | 878 | 642 |
| Relationships | 0.014 | 0.115 | 0.025 | 11 | 781 | 96 |

Type accuracy on matched entities: **0.860** (parent category: 0.860). Gold relationship pairs connected by any edge: 76 of 96. ASSOCIATED_WITH share of predicted edges: 97.4%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Date | 0.649 | 0.984 | 0.782 | 124 | 191 | 126 |
| Document | 0.200 | 0.059 | 0.091 | 2 | 10 | 34 |
| Domain | 0.500 | 1.000 | 0.667 | 1 | 2 | 1 |
| Drone | 0.000 | 0.000 | 0.000 | 0 | 0 | 1 |
| Event | 1.000 | 0.250 | 0.400 | 3 | 3 | 12 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 15 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.786 | 0.876 | 0.829 | 162 | 206 | 185 |
| Organization | 0.445 | 0.844 | 0.583 | 146 | 328 | 173 |
| Person | 0.437 | 0.912 | 0.591 | 31 | 71 | 34 |
| Product | 0.000 | 0.000 | 0.000 | 0 | 7 | 0 |
| Quantity | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| Ship | 1.000 | 0.540 | 0.701 | 27 | 27 | 50 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| Technology | 0.000 | 0.000 | 0.000 | 0 | 0 | 3 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Weapon | 0.000 | 0.000 | 0.000 | 0 | 0 | 10 |

## Type confusion (gold -> predicted)

- Location -> Organization: 15
- Ship -> Person: 13
- Document -> Organization: 9
- Weapon -> Organization: 7
- Ship -> Organization: 6
- Event -> Organization: 5
- Organization -> Location: 4
- Organization -> Person: 4
- Location -> Person: 3
- Event -> Location: 3
- Ship -> Location: 2
- Document -> Location: 2
- Document -> Date: 2
- Drone -> Organization: 1
- Person -> Organization: 1
- Organization -> Domain: 1
- Weapon -> Product: 1
- Technology -> Organization: 1
- Technology -> Location: 1
- Person -> Location: 1
- Ship -> Product: 1

## Relationships

Predicted types: ASSOCIATED_WITH 761, USES 6, TARGETS 5, OCCURRED_ON 3, SUPPLIED_BY 2, ATTRIBUTED_TO 1, EXPLOITS 1, LOCATED_AT 1, BELONGS_TO 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 1 | 2 |
| BELONGS_TO | 1 | 36 |
| COMMANDED_BY | 0 | 3 |
| DEPLOYED_AT | 0 | 6 |
| EXPLOITS | 1 | 1 |
| FUNDED_BY | 0 | 1 |
| LOCATED_AT | 1 | 13 |
| SUPPLIED_BY | 0 | 5 |
| TARGETS | 3 | 23 |
| USES | 4 | 6 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 17, retired 3, dropped 13 {'ASSOCIATED_WITH': 13}; entities created 662, filtered 8, dates orphaned 190.

## Cyber documents in full

### volt_typhoon_1

- mistyped: none
- missed: CISA [Organization]
- extra: none
- edges: 185.220.101.42 -ASSOCIATED_WITH-> evil-c2.com; China -ASSOCIATED_WITH-> Guam; Fortinet -ASSOCIATED_WITH-> CVE-2023-27997; Microsoft -ASSOCIATED_WITH-> CVE-2023-27997; Microsoft -ASSOCIATED_WITH-> Fortinet; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam
- gold edges missed: none
- build: created 3, dropped 0 {}

### volt_typhoon_2

- mistyped: none
- missed: AA23-144a [Document], ASUS [Organization], CISA [Organization]
- extra: none
- edges: Cisco -ASSOCIATED_WITH-> Netgear; Fortinet FortiGuard -ASSOCIATED_WITH-> CVE-2023-27997; Guam -ASSOCIATED_WITH-> United States; People's Republic of China -ASSOCIATED_WITH-> Guam; People's Republic of China -ASSOCIATED_WITH-> Volt Typhoon; Volt Typhoon -ASSOCIATED_WITH-> United States; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic; netsh -ASSOCIATED_WITH-> ntdsutil; netsh -ASSOCIATED_WITH-> wmic; ntdsutil -ASSOCIATED_WITH-> wmic
- gold edges missed: Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> United States
- build: created 4, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: none
- edges: Guam -ASSOCIATED_WITH-> Asia; Guam -ASSOCIATED_WITH-> United States; Kaohsiung -ASSOCIATED_WITH-> Manila; Kaohsiung -ASSOCIATED_WITH-> Taiwan; Microsoft -ASSOCIATED_WITH-> Naval Base Guam; NSA -ASSOCIATED_WITH-> Guam; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE -ASSOCIATED_WITH-> 45.83.12.7; Taiwan -ASSOCIATED_WITH-> Manila; United States -ASSOCIATED_WITH-> Asia; Volt Typhoon -ASSOCIATED_WITH-> Guam; Volt Typhoon -ASSOCIATED_WITH-> United States; Volt Typhoon -USES-> Windows; Windows -ASSOCIATED_WITH-> Kaohsiung; Windows -ASSOCIATED_WITH-> Taiwan
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 1, dropped 0 {}

## openrep: most frequent misses, extras and mistypes

Missed: JCPOA [Document] x3, E.O. 14347 [Document] x2, GCHQ [Organization] x1, H.R. 8610 [Document] x1, National Defense Strategy [Document] x1, United States [Location] x1, Allied Maritime Analysis Cell [Organization] x1, Partner Programmes Cell [Organization] x1, Takaichi [Person] x1, E3 [Organization] x1, SIG-OAR [Organization] x1, Resolution 2758 [Document] x1, CFIUS [Organization] x1, E.O. 13873 [Document] x1, E.O. 13942 [Document] x1.

Extra: Trump Administration [Organization] x5, China [Location] x5, 2026 [Date] x4, CRS [Organization] x4, DOD [Organization] x3, National Security [Organization] x3, Tehran [Location] x3, 2023 [Date] x3, Moscow [Location] x3, 2018 [Date] x2, Department [Organization] x2, IAEA [Organization] x2, Hormuz [Person] x2, Strait [Location] x2, Strait of [Location] x2.

Mistyped (gold -> predicted): Document -> Organization x9, Weapon -> Organization x7, Location -> Organization x6, Ship -> Organization x6, Event -> Organization x5, Organization -> Location x4, Organization -> Person x4, Event -> Location x3, Location -> Person x2, Document -> Location x2.

## kestrel: most frequent misses, extras and mistypes

Missed: 19th Signals Regiment [Organization] x3, 7th Composite Aviation Detachment [Organization] x3, 15-18 August [Date] x1.

Extra: Comparison [Organization] x3, Liaison [Person] x2, E03 [Organization] x1, approximately 20 per cent [Financial] x1, approximately 10 per cent [Financial] x1, approximately 30 per cent [Financial] x1, some 600 metres [Quantity] x1.

Mistyped (gold -> predicted): Ship -> Person x13, Location -> Organization x9, Ship -> Location x1, Location -> Person x1.
