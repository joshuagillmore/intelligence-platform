# Corpus extraction eval — `nlp`

Generated 2026-10-01T01:45:07+00:00 at `be263d08`; spaCy `en_core_web_sm`.

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.715 | 0.894 | 0.795 | 118 | 165 | 132 |
| Entities (name + type) | 0.376 | 0.470 | 0.417 | 62 | 165 | 132 |
| Relationships | 0.012 | 0.043 | 0.018 | 1 | 86 | 23 |
| corpus: entities | 0.651 | 0.925 | 0.764 | 86 | 132 | 93 |
| corpus: entities typed | 0.280 | 0.398 | 0.329 | 37 | 132 | 93 |
| corpus: relationships | 0.000 | 0.000 | 0.000 | 0 | 53 | 10 |
| cyber: entities | 0.970 | 0.821 | 0.889 | 32 | 33 | 39 |
| cyber: entities typed | 0.758 | 0.641 | 0.694 | 25 | 33 | 39 |
| cyber: relationships | 0.030 | 0.077 | 0.043 | 1 | 33 | 13 |

Type accuracy on matched entities: **0.525** (parent category: 0.525). Gold relationship pairs connected by any edge: 13 of 23. ASSOCIATED_WITH share of predicted edges: 98.8%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Date | 0.120 | 1.000 | 0.214 | 3 | 25 | 3 |
| Document | 0.000 | 0.000 | 0.000 | 0 | 0 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Hardware | 0.000 | 0.000 | 0.000 | 0 | 0 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.767 | 0.697 | 0.730 | 23 | 30 | 33 |
| Organization | 0.419 | 0.756 | 0.539 | 31 | 74 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 27 | 0 |
| Quantity | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Ship | 0.000 | 0.000 | 0.000 | 0 | 0 | 40 |
| Software | 0.000 | 0.000 | 0.000 | 0 | 0 | 4 |
| ThreatActor | 0.000 | 0.000 | 0.000 | 0 | 0 | 3 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Person: 21
- Ship -> Organization: 16
- Location -> Organization: 9
- ThreatActor -> Organization: 3
- Ship -> Location: 2
- Hardware -> Organization: 2
- Location -> Person: 1
- Organization -> Location: 1
- Software -> Location: 1

## Relationships

Predicted types: ASSOCIATED_WITH 85, TARGETS 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 0 | 2 |
| BELONGS_TO | 0 | 1 |
| EXPLOITS | 0 | 1 |
| LOCATED_AT | 0 | 10 |
| TARGETS | 1 | 5 |
| USES | 0 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 1, retired 0, dropped 14 {'ASSOCIATED_WITH': 14}; entities created 137, filtered 0, dates orphaned 25.

## Cyber documents in full

### volt_typhoon_1

- mistyped: Volt Typhoon: ThreatActor -> Organization
- missed: CISA [Organization]
- extra: May 2023 [Date]
- edges: 185.220.101.42 -ASSOCIATED_WITH-> evil-c2.com; 24 May 2023 -ASSOCIATED_WITH-> May 2023; China -ASSOCIATED_WITH-> 2023; China -ASSOCIATED_WITH-> Guam; Fortinet -ASSOCIATED_WITH-> CVE-2023-27997; Guam -ASSOCIATED_WITH-> 2023; Microsoft -ASSOCIATED_WITH-> CVE-2023-27997; Microsoft -ASSOCIATED_WITH-> Fortinet; NSA -ASSOCIATED_WITH-> 24 May 2023; NSA -ASSOCIATED_WITH-> May 2023; Volt Typhoon -ASSOCIATED_WITH-> China; Volt Typhoon -TARGETS-> Guam
- gold edges missed: Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -EXPLOITS-> CVE-2023-27997
- build: created 1, dropped 5 {'ASSOCIATED_WITH': 5}

### volt_typhoon_2

- mistyped: Cisco: Organization -> Location, Fortinet FortiGuard: Hardware -> Organization, Volt Typhoon: ThreatActor -> Organization
- missed: AA23-144a [Document], ASUS [Organization], CISA [Organization], netsh [Software], ntdsutil [Software], wmic [Software]
- extra: none
- edges: Cisco -ASSOCIATED_WITH-> Netgear; Fortinet FortiGuard -ASSOCIATED_WITH-> CVE-2023-27997; Guam -ASSOCIATED_WITH-> United States; People's Republic of China -ASSOCIATED_WITH-> Guam; People's Republic of China -ASSOCIATED_WITH-> Volt Typhoon; Volt Typhoon -ASSOCIATED_WITH-> Guam; Volt Typhoon -ASSOCIATED_WITH-> United States
- gold edges missed: Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> wmic
- build: created 0, dropped 0 {}

### volt_typhoon_3

- mistyped: Netgear ProSAFE: Hardware -> Organization, Volt Typhoon: ThreatActor -> Organization, Windows: Software -> Location
- missed: none
- extra: none
- edges: Guam -ASSOCIATED_WITH-> Asia; Guam -ASSOCIATED_WITH-> United States; Kaohsiung -ASSOCIATED_WITH-> Manila; Kaohsiung -ASSOCIATED_WITH-> Taiwan; Microsoft -ASSOCIATED_WITH-> Naval Base Guam; NSA -ASSOCIATED_WITH-> Guam; NSA -ASSOCIATED_WITH-> Volt Typhoon; Netgear ProSAFE -ASSOCIATED_WITH-> 45.83.12.7; Taiwan -ASSOCIATED_WITH-> Manila; United States -ASSOCIATED_WITH-> Asia; Volt Typhoon -ASSOCIATED_WITH-> Guam; Volt Typhoon -ASSOCIATED_WITH-> United States; Windows -ASSOCIATED_WITH-> Kaohsiung; Windows -ASSOCIATED_WITH-> Taiwan
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Naval Base Guam; Volt Typhoon -USES-> Windows
- build: created 0, dropped 0 {}

## Corpus: most frequent misses and extras

Missed: 19th Signals Regiment [Organization] x3, 7th Composite Aviation Detachment [Organization] x3, Hallgrim [Ship] x1.

Extra: quay 4 [Location] x3, Comparison [Organization] x3, AIS [Organization] x3, Valdorian [Organization] x3, liaison [Person] x3, 6 months [Date] x2, 3 days earlier [Date] x2, preceding week [Date] x2, Liaison [Person] x2, quarterly [Date] x2, 14 months [Date] x2, between 1624Z and 0028Z [Date] x1, E03 [Organization] x1, approximately 20 per cent [Financial] x1, 14 days earlier [Date] x1.
