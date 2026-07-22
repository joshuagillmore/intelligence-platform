# ATT&CK Phase 3 — Plan (CVE→ATT&CK chain · defensive view · ATT&CK product)

Extends `docs/design/specs/2026-07-22-mitre-attack-integration-design.md`. Built in
two coherent branches. All data keyless + redistributable (MITRE Terms of Use;
attribution in `data/attack/ATTRIBUTION.md`, extended to CWE™/CAPEC™/D3FEND™).

## 3a — CVE → ATT&CK chaining (branch `feat/attack-p3-cve`)

Chain NVD-enriched `Vulnerability` (CVE) entities to techniques via the canonical
CWE→CAPEC→ATT&CK path (covers any CVE with a CWE; broader than the sparse CTID KEV
direct map, which is deferred).

- **CVE→CWE (code fix):** `enrichment/providers/nvd.py` fetches but drops NVD's
  `cve.weaknesses[]`. Parse `description[].value` matching `^CWE-\d+$` → store
  `props["cwe_ids"]`. ~10 lines, no new request/dep.
- **CWE→CAPEC→ATT&CK (ingest):** fetch-on-demand (gitignored cache, like the ATT&CK
  bundle) `cwec_latest.xml.zip` (~4 MB) + `capec_latest.xml` (~6 MB); parse with
  stdlib `xml.etree.ElementTree` + `zipfile`. CWE `<Related_Attack_Patterns>` →
  CAPEC; CAPEC `<Taxonomy_Mappings Taxonomy_Name="ATTACK">` `<Entry_ID>` (numeric,
  e.g. `1566`→`T1566`) → technique. Build a CWE→[technique-ids] map; load global
  `(:Cwe {cwe_id,name})-[:ENABLES]->(:AttackTechnique)` reference edges.
- **Resolve (per project):** `(:Vulnerability {cwe_ids})` → MERGE
  `(:Vulnerability)-[:HAS_WEAKNESS]->(:Cwe)` and materialize
  `(:Vulnerability)-[:ENABLES {via:"cwe-capec"}]->(:AttackTechnique)`.
- **Keep CVE-enabled techniques SEPARATE from TTP-observed** (don't conflate "we saw
  this behavior" with "an in-scope CVE could enable it"). Surface in technique detail
  as `enabling_cves`; do NOT fold into `observed_count`.
- **API:** `POST /attack/ingest-vuln-chain` (admin), `POST /attack/resolve-cve?project_id=`,
  and `enabling_cves` added to `GET /attack/technique/{tid}`.
- **Frontend:** technique drawer shows "CVEs that enable this technique"; the CVE/IOC
  row (cyber) can show "enables N ATT&CK techniques".

## 3b — Defensive view: D3FEND + M-codes (branch `feat/attack-p3-defense`)

We already ingest ATT&CK Mitigations (M-codes) + `MITIGATES` edges. Add D3FEND
countermeasures (finer-grained, ~250) fetched **lazily, keyless**, no vendored 10 MB.

- **API:** `GET /attack/technique/{tid}/d3fend` → fetch
  `d3fend.mitre.org/api/offensive-technique/attack/{Txxxx}.json` via ProxiedClient,
  parse to `[{d3fend_id, label}]`, cache (Postgres, like the enrichment cache).
  Degrade to `[]` on outage.
- **Frontend:** a "Defenses" section in the technique drawer — the M-code mitigations
  (already available) + a lazy "Load D3FEND countermeasures" button.

## 3c — ATT&CK-structured intelligence product (branch `feat/attack-p3-defense`)

- **API:** `GET /attack/report?project_id=` — assemble from the graph: observed
  techniques grouped by tactic, top attribution candidates (Phase 2), key mitigations,
  and CVE→technique links; add a short LLM-generated narrative (reuse `report_writing`
  skill via the orchestrator; degrade to the structured data if no LLM). Returns
  structured JSON + markdown.
- **Frontend:** a "Generate ATT&CK Report" action (matrix/products) that renders the
  structured product with a Navigator-layer download + markdown export.

## Decisions
- CTID KEV direct CVE→ATT&CK: **deferred** (sparse ~28%, ~1yr stale); CWE→CAPEC covers breadth.
- D3FEND: **lazy per-technique fetch** (no vendored dataset) — keeps the repo lean.
- CVE-enabled ≠ observed: kept as distinct edges + UI so the matrix isn't inflated.
- All fetches config-pinned hosts through ProxiedClient; caches gitignored.
