# MITRE ATT&CK® Integration — Design

**Date:** 2026-07-22
**Status:** Phase 1 in progress
**Related:** `docs/design/specs/2026-07-19-cyber-investigations-unification-design.md`

## Problem

The `/cyber` page has an **ATT&CK Matrix** tab, but it is a hardcoded shell:
~26 techniques across 8 tactics defined inline in `frontend/src/app/cyber/page.tsx`
(`MITRE_TACTICS`), with "coverage" inferred by substring-matching a `TTP` entity's
name against a technique ID. Real ATT&CK Enterprise is **14 tactics, ~200
techniques, ~450 sub-techniques**, plus Groups (APTs), Software, and Mitigations.

We want ATT&CK to be a *real, graph-grounded* part of the platform: the canonical
model living in Neo4j alongside collected intel, extracted TTPs resolved to
canonical technique IDs, and analysis (matrix, attribution, Navigator export)
driven off the graph.

## Data source & license

- **Source:** `mitre-attack/attack-stix-data` (STIX 2.1). Enterprise domain bundle,
  **pinned to a versioned filename** for reproducibility (e.g.
  `enterprise-attack-19.1.json`), fetched from
  `raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/<file>`.
- **Keyless, commercial-OK, redistributable** under the ATT&CK Terms of Use, **with
  attribution**: reproduce verbatim
  `© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.`
  and use "MITRE ATT&CK®" on first reference. Attribution ships in
  `data/attack/ATTRIBUTION.md` and is surfaced in the UI.
- **Bundle is ~50 MB** → NOT committed to the repo (portfolio repo stays lean).
  **Fetched on demand** at ingest time (a manual admin action) via the collection
  `ProxiedClient`, cached to a gitignored path, pinned by version in config.
- Parsed with **stdlib `json`** — no `mitreattack-python` (it drags in
  stix2/pandas/deepdiff; overkill for a one-way load). Two linear passes over the
  flat `objects` array.

## Graph model

ATT&CK reference data is **global** (not per-project), so it uses **dedicated
reference labels** with an `attack_id` key and **no `project_id`** — kept separate
from observed, per-project intel:

| Label | STIX type | ID | Key fields |
|-------|-----------|-----|-----------|
| `AttackTactic` | `x-mitre-tactic` | `TA####` | name, `shortname` (join key), description |
| `AttackTechnique` | `attack-pattern` | `T####[.###]` | name, description, is_subtechnique, platforms, detection |
| `AttackGroup` | `intrusion-set` | `G####` | name, aliases, description |
| `AttackSoftware` | `malware`/`tool` | `S####` | name, software_type, platforms |
| `AttackMitigation` | `course-of-action` | `M####` | name, description |

Relationships (canonical model):
- `(AttackTechnique)-[:PART_OF_TACTIC]->(AttackTactic)` — from `kill_chain_phases`
  `phase_name` → tactic `shortname` (a technique may span multiple tactics).
- `(AttackTechnique)-[:SUBTECHNIQUE_OF]->(AttackTechnique)` — from `subtechnique-of`.
- `(AttackGroup|AttackSoftware)-[:USES]->(AttackTechnique)`, `(AttackGroup)-[:USES]->(AttackSoftware)` — from `uses`.
- `(AttackMitigation)-[:MITIGATES]->(AttackTechnique)` — from `mitigates`.

**Bridge to observed intel:** `(TTP|ThreatActor)-[:MAPS_TO]->(AttackTechnique|AttackGroup)`
— a per-project entity resolved to its canonical ATT&CK node.

**Ingest rules:** `attack_id` from `external_references[source_name=="mitre-attack"].external_id`
(never the STIX id). Skip objects where `revoked` or `x_mitre_deprecated` is true
(and any relationship whose endpoints were skipped). Idempotent `MERGE` on
`attack_id` + a uniqueness constraint per label, so re-ingest across version bumps
is safe.

## TTP resolution

Project `TTP` entities are extracted from reporting with names that often contain a
technique ID ("T1566", "T1566.001 Spearphishing"). A resolver extracts the T-code
via regex and `MERGE`s a `MAPS_TO` edge to the matching `AttackTechnique`. Runs on
demand (`POST /attack/resolve`) and after ingest. (Phase 2 adds LLM/RAG text→technique
mapping for prose without explicit IDs — out of scope here.)

## API (`api/routes/attack.py`)

- `GET  /attack/status` — ingested? version, node counts.
- `POST /attack/ingest` — (admin) fetch + parse + load the pinned bundle. Idempotent.
- `POST /attack/resolve?project_id=` — link this project's TTP/ThreatActor entities to canonical nodes.
- `GET  /attack/matrix?project_id=` — full tactic→technique model + per-technique
  observed-coverage (count of mapped project TTPs). Drives the matrix UI.
- `GET  /attack/technique/{tid}?project_id=` — detail: description, tactics, mitigations,
  groups that use it, and related project entities.
- `GET  /attack/navigator-layer?project_id=` — export a Navigator **layer v4.5** JSON
  (`techniqueID`+`score`+`tactic`+`comment`, gradient header) that opens in the hosted Navigator.

## Frontend

Rewrite the `/cyber` **ATT&CK Matrix** tab to be data-driven from `/attack/matrix`
(full matrix, coverage-colored by observed count), technique detail from
`/attack/technique/{tid}` (mitigations, groups, related project entities), a
**Download Navigator layer** button, and — when ATT&CK is not yet ingested — an
"Ingest ATT&CK data" affordance (admin). The hardcoded `MITRE_TACTICS` is removed.

## Phasing

- **Phase 1 (this spec):** ingest + graph model + TTP-ID resolution + `/attack` API +
  data-driven matrix + Navigator export.
- **Phase 2:** LLM/RAG text→technique mapping (prose without IDs); threat-actor
  attribution by TTP-overlap vs ATT&CK Groups.
- **Phase 3:** CVE→CWE→CAPEC→ATT&CK chaining off NVD enrichment; Mitigations/D3FEND
  defensive view; ATT&CK-structured intelligence products.

## Out of scope / deferred

Mobile & ICS domains (Enterprise only for now); committing the bundle; graphing
revoked/deprecated history; the Phase 2/3 items above.
