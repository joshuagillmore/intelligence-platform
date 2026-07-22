"""CVE→ATT&CK chaining through the canonical CWE→CAPEC→ATT&CK path.

An NVD-enriched ``Vulnerability`` carries ``cwe_ids`` (see
``enrichment/providers/nvd.py``). MITRE's CAPEC maps each attack pattern to the
CWEs it targets *and* to the ATT&CK techniques it realizes, so pivoting through
CAPEC yields a ``CWE → {technique}`` map that chains any CWE-tagged CVE to the
techniques it could enable.

This module:
  1. fetches (on demand, cached, keyless) the CWE and CAPEC XML datasets,
  2. builds the ``cwe_id → {technique_id}`` map (+ ``cwe_id → name``),
  3. loads global ``(:Cwe)-[:ENABLES]->(:AttackTechnique)`` reference edges, and
  4. per project, materializes ``(:Vulnerability)-[:HAS_WEAKNESS]->(:Cwe)`` and
     ``(:Vulnerability)-[:ENABLES {via:"cwe-capec"}]->(:AttackTechnique)``.

CVE-enabled techniques are kept **separate** from TTP-observed coverage — they
say "an in-scope CVE could enable this", never "we saw this behavior".

CWE™ and CAPEC™ are trademarks of The MITRE Corporation, used under the MITRE
Terms of Use — see ``data/attack/ATTRIBUTION.md``. Both files are keyless and
redistributable; the fetched copies are cached to a gitignored path and never
committed.

Sync Neo4j helpers take a ``Driver`` so async callers offload with
``asyncio.to_thread``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from neo4j import Driver

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings

from .graph_ops import VULN_CHAIN_META_ID

logger = logging.getLogger(__name__)

# repo-root/data/attack — same cache dir as the ATT&CK bundle. __file__ is
# backend/src/intel_platform/services/attack/vuln_chain.py → parents[5] is the root.
_DATA_DIR = Path(__file__).resolve().parents[5] / "data" / "attack"
_CAPEC_CACHE = _DATA_DIR / "capec_latest.xml"
_CWE_CACHE = _DATA_DIR / "cwec_latest.xml.zip"

_CWE_ID_RE = re.compile(r"^CWE-\d+$")


def _local(tag: str) -> str:
    """Strip an XML namespace from a tag: ``{ns}Weakness`` → ``Weakness``.

    Both datasets are namespaced (CWE ``cwe-7``, CAPEC ``capec-3``); stripping
    the ``{ns}`` makes the parser robust to a namespace-version bump.
    """
    return tag.rpartition("}")[2]


# --- Parsing (pure; no network) --------------------------------------------

def parse_capec(capec_xml: str) -> dict[str, set[str]]:
    """Build ``cwe_id → {technique_id}`` by pivoting through CAPEC.

    For each ``<Attack_Pattern>`` collect (a) its ATT&CK technique ids — the
    numeric ``<Entry_ID>`` under a ``<Taxonomy_Mapping Taxonomy_Name="ATTACK">``,
    prefixed ``T`` (so ``1059`` → ``T1059`` and the sub-technique ``1059.001`` →
    ``T1059.001``) — and (b) its related CWE ids (``<Related_Weakness
    CWE_ID="78"/>`` → ``CWE-78``). Every technique the pattern maps to applies to
    each of its related CWEs. Patterns with no ATT&CK mapping contribute nothing.
    """
    root = ET.fromstring(capec_xml)
    mapping: dict[str, set[str]] = defaultdict(set)
    for ap in root.iter():
        if _local(ap.tag) != "Attack_Pattern":
            continue
        tids: set[str] = set()
        cwes: set[str] = set()
        for el in ap.iter():
            lt = _local(el.tag)
            if lt == "Taxonomy_Mapping" and el.get("Taxonomy_Name") == "ATTACK":
                for child in el:
                    if _local(child.tag) == "Entry_ID":
                        entry = (child.text or "").strip()
                        if entry:
                            tids.add(f"T{entry}")
            elif lt == "Related_Weakness":
                cwe = (el.get("CWE_ID") or "").strip()
                if cwe:
                    cwes.add(f"CWE-{cwe}")
        if not tids:
            continue
        for cwe in cwes:
            mapping[cwe].update(tids)
    return dict(mapping)


def parse_cwe_names(cwe_xml: str) -> dict[str, str]:
    """Build ``cwe_id → name`` from the CWE ``<Weakness_Catalog>``.

    Each ``<Weakness ID="79" Name="...">`` → ``CWE-79 → "..."``.
    """
    root = ET.fromstring(cwe_xml)
    names: dict[str, str] = {}
    for el in root.iter():
        if _local(el.tag) != "Weakness":
            continue
        cid = (el.get("ID") or "").strip()
        if cid:
            names[f"CWE-{cid}"] = el.get("Name") or ""
    return names


def build_map(capec_xml: str, cwe_xml: str) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Parse both files → ``(cwe_id → {technique_id}, cwe_id → name)``."""
    return parse_capec(capec_xml), parse_cwe_names(cwe_xml)


# --- Fetch (on demand, cached) ---------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError:
        logger.warning("Could not cache %s", path, exc_info=True)


def _write_bytes(path: Path, content: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except OSError:
        logger.warning("Could not cache %s", path, exc_info=True)


def _read_zip_xml(path: Path) -> str:
    """Return the XML text of the first ``.xml`` member of a cached zip."""
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        member = members[0] if members else zf.namelist()[0]
        return zf.read(member).decode("utf-8")


async def _load_capec_xml() -> str:
    if _CAPEC_CACHE.exists():
        logger.info("Loading cached CAPEC %s", _CAPEC_CACHE.name)
        return await asyncio.to_thread(_read_text, _CAPEC_CACHE)
    logger.info("Fetching CAPEC from %s", settings.capec_xml_url)
    resp = await ProxiedClient().get(settings.capec_xml_url, timeout=120)
    resp.raise_for_status()
    text = resp.text
    await asyncio.to_thread(_write_text, _CAPEC_CACHE, text)
    return text


async def _load_cwe_xml() -> str:
    if not _CWE_CACHE.exists():
        logger.info("Fetching CWE from %s", settings.cwe_xml_url)
        resp = await ProxiedClient().get(settings.cwe_xml_url, timeout=120)
        resp.raise_for_status()
        await asyncio.to_thread(_write_bytes, _CWE_CACHE, resp.content)
    else:
        logger.info("Loading cached CWE %s", _CWE_CACHE.name)
    return await asyncio.to_thread(_read_zip_xml, _CWE_CACHE)


# --- Load reference edges (Neo4j; idempotent) ------------------------------

def load_vuln_chain(
    driver: Driver, cwe_to_techs: dict[str, set[str]], cwe_names: dict[str, str]
) -> dict:
    """Idempotently load ``(:Cwe)-[:ENABLES]->(:AttackTechnique)`` reference edges.

    A ``Cwe`` node is MERGEd for every CWE in the pivot map (named from the CWE
    catalog when available). An ``ENABLES`` edge is created only where the mapped
    technique already EXISTS as an ``AttackTechnique`` node — unknown/revoked
    technique ids are skipped. A ``VulnChainMeta`` singleton records the counts.
    Returns ``{"cwes": int, "edges": int}``.
    """
    now = datetime.now(timezone.utc).isoformat()
    cwe_rows = [{"cwe_id": cid, "name": cwe_names.get(cid, "")} for cid in cwe_to_techs]
    edge_rows = [
        {"cwe_id": cid, "tid": tid}
        for cid, tids in cwe_to_techs.items()
        for tid in tids
    ]

    with driver.session() as session:
        if cwe_rows:
            session.run(
                """
                UNWIND $rows AS r
                MERGE (c:Cwe {cwe_id: r.cwe_id})
                SET c.name = r.name
                """,
                rows=cwe_rows,
            )
        edges = 0
        if edge_rows:
            rec = session.run(
                """
                UNWIND $rows AS r
                MATCH (c:Cwe {cwe_id: r.cwe_id})
                MATCH (tech:AttackTechnique {attack_id: r.tid})
                MERGE (c)-[:ENABLES]->(tech)
                RETURN count(*) AS edges
                """,
                rows=edge_rows,
            ).single()
            edges = rec["edges"] if rec else 0

        session.run(
            """
            MERGE (m:VulnChainMeta {id: $id})
            SET m.cwes = $cwes, m.edges = $edges, m.ingested_at = $now
            """,
            id=VULN_CHAIN_META_ID, cwes=len(cwe_rows), edges=edges, now=now,
        )

    return {"cwes": len(cwe_rows), "edges": edges}


async def ingest_vuln_chain(driver: Driver) -> dict:
    """Fetch (or load cached) CWE+CAPEC, build the map, load reference edges.

    The ~35 MB CWE + ~6 MB CAPEC parses and the Neo4j load are CPU/IO-bound and
    offloaded with ``asyncio.to_thread`` so they never block the event loop; only
    the network fetch itself runs on the loop.
    """
    capec_xml = await _load_capec_xml()
    cwe_xml = await _load_cwe_xml()
    cwe_to_techs, cwe_names = await asyncio.to_thread(build_map, capec_xml, cwe_xml)
    return await asyncio.to_thread(load_vuln_chain, driver, cwe_to_techs, cwe_names)


# --- Per-project resolve ---------------------------------------------------

def _normalize_cwe_ids(raw: object) -> list[str]:
    """Normalize a ``Vulnerability.cwe_ids`` prop to a deduped list of ``CWE-\\d+``.

    Enrichment writes it as a native Neo4j list, but a JSON-string encoding is
    tolerated too (other write paths may serialize the list). Non-``CWE-\\d+``
    values are dropped.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            parsed: object = json.loads(raw)
        except (ValueError, TypeError):
            parsed = raw
        if isinstance(parsed, str):
            values: list = [parsed]
        elif isinstance(parsed, (list, tuple)):
            values = list(parsed)
        else:
            return []
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = str(v).strip()
        if _CWE_ID_RE.match(s) and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def resolve_cve(driver: Driver, project_id: str) -> dict:
    """Materialize a project's CVE→ATT&CK links through CWE→CAPEC.

    For each project ``Vulnerability`` carrying ``cwe_ids``:
      - MERGE ``(:Vulnerability)-[:HAS_WEAKNESS]->(:Cwe {cwe_id})``, and
      - MERGE ``(:Vulnerability)-[:ENABLES {via:"cwe-capec"}]->(:AttackTechnique)``
        for every technique its CWEs ``ENABLES`` (reference edges from ingest).

    Idempotent; batched via UNWIND (no per-node round trips). Returns the number
    of vulnerabilities resolved and the number of CVE→technique edges materialized.
    """
    with driver.session() as session:
        vulns = session.run(
            """
            MATCH (v:Vulnerability {project_id: $pid})
            WHERE v.cwe_ids IS NOT NULL
            RETURN v.id AS id, v.cwe_ids AS cwe_ids
            """,
            pid=project_id,
        ).data()

        pairs = [
            {"vid": v["id"], "cwe_id": cwe}
            for v in vulns
            for cwe in _normalize_cwe_ids(v["cwe_ids"])
        ]
        if not pairs:
            return {"vulnerabilities": 0, "techniques_linked": 0}

        vrec = session.run(
            """
            UNWIND $pairs AS p
            MATCH (v:Vulnerability {id: p.vid})
            MERGE (c:Cwe {cwe_id: p.cwe_id})
            MERGE (v)-[:HAS_WEAKNESS]->(c)
            RETURN count(DISTINCT v) AS vulns
            """,
            pairs=pairs,
        ).single()
        vulns_linked = vrec["vulns"] if vrec else 0

        session.run(
            """
            UNWIND $pairs AS p
            MATCH (v:Vulnerability {id: p.vid})-[:HAS_WEAKNESS]->
                  (:Cwe {cwe_id: p.cwe_id})-[:ENABLES]->(tech:AttackTechnique)
            MERGE (v)-[:ENABLES {via: 'cwe-capec'}]->(tech)
            """,
            pairs=pairs,
        )

        trec = session.run(
            """
            MATCH (:Vulnerability {project_id: $pid})-[e:ENABLES {via: 'cwe-capec'}]->(:AttackTechnique)
            RETURN count(e) AS links
            """,
            pid=project_id,
        ).single()
        techniques_linked = trec["links"] if trec else 0

    return {"vulnerabilities": vulns_linked, "techniques_linked": techniques_linked}
