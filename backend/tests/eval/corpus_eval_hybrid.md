# Corpus extraction eval — `hybrid`

Generated 2026-10-01T02:01:41+00:00 at `be263d08`; spaCy `en_core_web_sm`; LLM `CohereProvider` / `command-a-plus-05-2026` (43 live replies, 0 replayed).

No document degraded: every score below is the requested mode's own.

| Metric | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Entities (name) | 0.355 | 0.992 | 0.523 | 131 | 369 | 132 |
| Entities (name + type) | 0.306 | 0.856 | 0.451 | 113 | 369 | 132 |
| Relationships | 0.063 | 0.870 | 0.118 | 20 | 317 | 23 |
| corpus: entities | 0.287 | 1.000 | 0.446 | 93 | 324 | 93 |
| corpus: entities typed | 0.241 | 0.839 | 0.374 | 78 | 324 | 93 |
| corpus: relationships | 0.036 | 1.000 | 0.069 | 10 | 281 | 10 |
| cyber: entities | 0.844 | 0.974 | 0.905 | 38 | 45 | 39 |
| cyber: entities typed | 0.778 | 0.897 | 0.833 | 35 | 45 | 39 |
| cyber: relationships | 0.278 | 0.769 | 0.408 | 10 | 36 | 13 |

Type accuracy on matched entities: **0.863** (parent category: 0.878). Gold relationship pairs connected by any edge: 22 of 23. ASSOCIATED_WITH share of predicted edges: 45.4%.

## Per type (name + type must match)

| Type | P | R | F1 | TP | Pred | Gold |
|---|---|---|---|---|---|---|
| Aircraft | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Attribute | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Campaign | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Classification | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Communication | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Condition | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| Date | 0.064 | 1.000 | 0.120 | 3 | 47 | 3 |
| Document | 0.000 | 0.000 | 0.000 | 0 | 4 | 1 |
| Domain | 1.000 | 1.000 | 1.000 | 1 | 1 | 1 |
| Equipment | 0.000 | 0.000 | 0.000 | 0 | 8 | 0 |
| Event | 0.000 | 0.000 | 0.000 | 0 | 100 | 0 |
| Financial | 0.000 | 0.000 | 0.000 | 0 | 2 | 0 |
| Hardware | 1.000 | 0.500 | 0.667 | 1 | 1 | 2 |
| IPAddress | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |
| Location | 0.579 | 1.000 | 0.733 | 33 | 57 | 33 |
| Organization | 0.565 | 0.951 | 0.709 | 39 | 69 | 41 |
| Person | 0.000 | 0.000 | 0.000 | 0 | 25 | 0 |
| Ship | 0.893 | 0.625 | 0.735 | 25 | 28 | 40 |
| Software | 1.000 | 1.000 | 1.000 | 4 | 4 | 4 |
| TTP | 0.000 | 0.000 | 0.000 | 0 | 5 | 0 |
| ThreatActor | 1.000 | 1.000 | 1.000 | 3 | 3 | 3 |
| Vehicle | 0.000 | 0.000 | 0.000 | 0 | 3 | 0 |
| Vulnerability | 1.000 | 1.000 | 1.000 | 2 | 2 | 2 |

## Type confusion (gold -> predicted)

- Ship -> Person: 10
- Ship -> Organization: 2
- Ship -> Vehicle: 2
- Ship -> Location: 1
- Organization -> Date: 1
- Document -> Event: 1
- Hardware -> Equipment: 1

## Relationships

Predicted types: ASSOCIATED_WITH 144, OCCURRED_ON 50, LOCATED_AT 35, MENTIONED_IN 23, USES 17, BELONGS_TO 15, TARGETS 12, DEPLOYED_AT 7, COMMUNICATES_WITH 5, ATTRIBUTED_TO 3, SUPPLIED_BY 3, EXPLOITS 2, ASSESSES 1.

| Gold type | Found | Gold |
|---|---|---|
| ATTRIBUTED_TO | 1 | 2 |
| BELONGS_TO | 1 | 1 |
| EXPLOITS | 1 | 1 |
| LOCATED_AT | 9 | 10 |
| TARGETS | 4 | 5 |
| USES | 4 | 4 |

## Graph build (real `build_graph_from_extractions`, throwaway projects)

Relationships created 246, retired 50, dropped 21 {'ASSOCIATED_WITH': 14, 'MENTIONED_IN': 4, 'BELONGS_TO': 2, 'LOCATED_AT': 1}; entities created 319, filtered 0, dates orphaned 44.

## Cyber documents in full

### volt_typhoon_1

- mistyped: May 2023: Organization -> Date
- missed: none
- extra: CISA-NSA joint advisory [Event], Guam telecommunications providers [Organization], Volt Typhoon targeting [Event], living-off-the-land techniques [TTP]
- edges: CISA -ASSOCIATED_WITH-> CISA-NSA joint advisory; CISA-NSA joint advisory -OCCURRED_ON-> 24 May 2023; Microsoft -ASSOCIATED_WITH-> Volt Typhoon; NSA -ASSOCIATED_WITH-> CISA-NSA joint advisory; Volt Typhoon -ATTRIBUTED_TO-> China; Volt Typhoon -COMMUNICATES_WITH-> 185.220.101.42; Volt Typhoon -COMMUNICATES_WITH-> evil-c2.com; Volt Typhoon -EXPLOITS-> CVE-2023-27997; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> Guam telecommunications providers; Volt Typhoon -USES-> living-off-the-land techniques; Volt Typhoon targeting -OCCURRED_ON-> 2023
- gold edges missed: none
- build: created 10, dropped 0 {}

### volt_typhoon_2

- mistyped: CISA Advisory AA23-144a: Document -> Event, Fortinet FortiGuard: Hardware -> Equipment
- missed: CISA [Organization]
- extra: small-office routers [Equipment]
- edges: CISA Advisory AA23-144a -MENTIONED_IN-> Volt Typhoon; CVE-2023-27997 -EXPLOITS-> Fortinet FortiGuard; Volt Typhoon -ASSOCIATED_WITH-> People's Republic of China; Volt Typhoon -TARGETS-> Guam; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> CVE-2023-27997; Volt Typhoon -USES-> netsh; Volt Typhoon -USES-> ntdsutil; Volt Typhoon -USES-> small-office routers; Volt Typhoon -USES-> wmic; small-office routers -SUPPLIED_BY-> ASUS; small-office routers -SUPPLIED_BY-> Cisco; small-office routers -SUPPLIED_BY-> Netgear
- gold edges missed: Volt Typhoon -ATTRIBUTED_TO-> People's Republic of China
- build: created 13, dropped 0 {}

### volt_typhoon_3

- mistyped: none
- missed: none
- extra: Naval Base Guam intrusions [Event], Volt Typhoon Guam campaign [Campaign]
- edges: Microsoft -ASSOCIATED_WITH-> Volt Typhoon Guam campaign; NSA -ATTRIBUTED_TO-> Volt Typhoon; Netgear ProSAFE router -LOCATED_AT-> 45.83.12.7; Netgear ProSAFE router -USES-> Volt Typhoon; Volt Typhoon -DEPLOYED_AT-> Kaohsiung; Volt Typhoon -DEPLOYED_AT-> Manila; Volt Typhoon -LOCATED_AT-> Guam networks; Volt Typhoon -TARGETS-> Asia; Volt Typhoon -TARGETS-> United States; Volt Typhoon -USES-> Windows; Volt Typhoon Guam campaign -ASSOCIATED_WITH-> Naval Base Guam intrusions
- gold edges missed: Kaohsiung -LOCATED_AT-> Taiwan; Volt Typhoon -TARGETS-> Naval Base Guam
- build: created 10, dropped 1 {'LOCATED_AT': 1}

## Corpus: most frequent misses and extras

Missed: none.

Extra: Source [Person] x5, Quay 4 [Location] x3, Apron [Location] x3, Partner [Organization] x3, Valdorian naval liaison [Person] x3, Collection gap [Event] x2, Transmission [Event] x2, Publication [Organization] x2, quay 1 [Location] x2, 3 affected sailings [Event] x2, Collection against Meran Strait [Event] x2, Partner service [Organization] x2, preparation for movement [Event] x2, fusion cell [Organization] x2, publicised national exercise [Event] x2.
