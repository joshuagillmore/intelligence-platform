# Corpus extraction eval — `nlp`

Generated 2026-10-01T03:20:03+00:00 at `ef68988d`; spaCy `en_core_web_sm`.

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.924 | 0.917 | 0.920 | 121 | 131 | 132 |
| Entities (name + type) | 0.741 | 0.735 | 0.738 | 97 | 131 | 132 |
| Relationships | 0.115 | 0.435 | 0.182 | 10 | 87 | 23 |
| corpus: entities | 0.896 | 0.925 | 0.910 | 86 | 96 | 93 |
| corpus: entities typed | 0.646 | 0.667 | 0.656 | 62 | 96 | 93 |
| corpus: relationships | 0.039 | 0.200 | 0.066 | 2 | 51 | 10 |
| cyber: entities | 1.000 | 0.897 | 0.946 | 35 | 35 | 39 |
| cyber: entities typed | 1.000 | 0.897 | 0.946 | 35 | 35 | 39 |
| cyber: relationships | 0.222 | 0.615 | 0.327 | 8 | 36 | 13 |

Type accuracy on matched entities: **0.802** (parent category: 0.802). Gold relationship pairs connected by any edge: 19 of 23. ASSOCIATED_WITH share of predicted edges: 88.5%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Date | 1.000 | 0.667 | 0.800 | 2 | 2 | 3 |
| Document | 0.000 | 0.000 | 0.000 | 0 | 0 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Hardware | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.958 | 0.697 | 0.807 | 23 | 24 | 33 |
| Organization | 0.711 | 0.780 | 0.744 | 32 | 45 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 16 | 0 |
| Quantity | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Ship | 1.000 | 0.650 | 0.788 | 26 | 26 | 40 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Person: 13
- Location -> Organization: 9
- Ship -> Location: 1
- Location -> Person: 1

## Relationships

Predicted types: ASSOCIATED_WITH 77, USES 4, TARGETS 2, LOCATED_AT 1, BELONGS_TO 1, ATTRIBUTED_TO 1, EXPLOITS 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 1 | 2 |
| BELONGS_TO | 1 | 1 |
| EXPLOITS | 1 | 1 |
| LOCATED_AT | 1 | 10 |
| TARGETS | 2 | 5 |
| USES | 4 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 10, retired 0, dropped 0 ; entities created 128, filtered 0, dates orphaned 2.

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

## Corpus: most frequent misses and extras

Missed: 19th Signals Regiment [Organization] x3, 7th Composite Aviation Detachment [Organization] x3, 15-18 August [Date] x1.

Extra: Comparison [Organization] x3, Liaison [Person] x2, E03 [Organization] x1, approximately 20 per cent [Financial] x1, approximately 10 per cent [Financial] x1, approximately 30 per cent [Financial] x1, some 600 metres [Quantity] x1.
