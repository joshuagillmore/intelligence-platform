"""Neo4j operations for the ATT&CK reference model.

The parsed model (from :mod:`stix_parser`) is loaded here as **global** reference
nodes — dedicated ``Attack*`` labels keyed by ``attack_id`` with **no
``project_id``** — kept separate from per-project observed intel. All writes are
idempotent ``MERGE``s so re-ingest across version bumps is safe.

Read helpers (matrix / technique detail / Navigator layer) join the global model
to a project's ``TTP``/``ThreatActor`` entities through the ``MAPS_TO`` bridge
written by :func:`resolve_ttps`.

Every function takes a Neo4j ``Driver`` (sync) so callers offload with
``asyncio.to_thread`` from async routes.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone

from neo4j import Driver

from .stix_parser import ParsedAttack

# attack_id -> label, used to type relationship MATCHes so they hit the per-label
# uniqueness index instead of an all-nodes scan. Values are from a fixed
# vocabulary (never user input) so they are safe to interpolate into Cypher.
_META_ID = "attack-meta"

# Technique-id / group-id patterns for resolving free-text project entities.
# \b-anchored so a longer digit run can't truncate to a valid-looking code
# (e.g. "T12345" must NOT match "T1234", "T1566.0012" must NOT match "T1566.001").
_TECH_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
_GROUP_RE = re.compile(r"\bG\d{4}\b")

_COUNT_LABELS = [
    ("AttackTactic", "tactics"),
    ("AttackTechnique", "techniques"),
    ("AttackGroup", "groups"),
    ("AttackSoftware", "software"),
    ("AttackMitigation", "mitigations"),
]


def _label_map(parsed: ParsedAttack) -> dict[str, str]:
    """Map every attack_id in the parsed model to its Neo4j label."""
    labels: dict[str, str] = {}
    for node in parsed.tactics:
        labels[node["attack_id"]] = "AttackTactic"
    for node in parsed.techniques:
        labels[node["attack_id"]] = "AttackTechnique"
    for node in parsed.groups:
        labels[node["attack_id"]] = "AttackGroup"
    for node in parsed.software:
        labels[node["attack_id"]] = "AttackSoftware"
    for node in parsed.mitigations:
        labels[node["attack_id"]] = "AttackMitigation"
    return labels


def ingest_model(driver: Driver, parsed: ParsedAttack, version: str) -> dict:
    """Idempotently load the parsed model into Neo4j. Returns node counts."""
    now = datetime.now(timezone.utc).isoformat()
    label_of = _label_map(parsed)

    with driver.session() as session:
        # --- Nodes (MERGE on attack_id per label) -------------------------
        session.run(
            """
            UNWIND $rows AS r
            MERGE (n:AttackTactic {attack_id: r.attack_id})
            SET n.name = r.name, n.shortname = r.shortname, n.description = r.description
            """,
            rows=parsed.tactics,
        )
        session.run(
            """
            UNWIND $rows AS r
            MERGE (n:AttackTechnique {attack_id: r.attack_id})
            SET n.name = r.name, n.description = r.description,
                n.is_subtechnique = r.is_subtechnique, n.platforms = r.platforms,
                n.detection = r.detection
            """,
            rows=parsed.techniques,
        )
        session.run(
            """
            UNWIND $rows AS r
            MERGE (n:AttackGroup {attack_id: r.attack_id})
            SET n.name = r.name, n.aliases = r.aliases, n.description = r.description
            """,
            rows=parsed.groups,
        )
        session.run(
            """
            UNWIND $rows AS r
            MERGE (n:AttackSoftware {attack_id: r.attack_id})
            SET n.name = r.name, n.software_type = r.software_type,
                n.platforms = r.platforms, n.description = r.description
            """,
            rows=parsed.software,
        )
        session.run(
            """
            UNWIND $rows AS r
            MERGE (n:AttackMitigation {attack_id: r.attack_id})
            SET n.name = r.name, n.description = r.description
            """,
            rows=parsed.mitigations,
        )

        # --- Technique -> Tactic (from kill_chain_phases) -----------------
        tech_tactics = [
            {"tech": t["attack_id"], "shortname": sn}
            for t in parsed.techniques
            for sn in t["tactic_shortnames"]
        ]
        session.run(
            """
            UNWIND $rows AS r
            MATCH (tech:AttackTechnique {attack_id: r.tech})
            MATCH (ta:AttackTactic {shortname: r.shortname})
            MERGE (tech)-[:PART_OF_TACTIC]->(ta)
            """,
            rows=tech_tactics,
        )

        # --- Typed relationships (USES / MITIGATES / SUBTECHNIQUE_OF) -----
        # Group by (source label, rel type, target label) so each MATCH is
        # label-typed and index-backed.
        combos: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for src, rel, dst in parsed.relationships:
            src_label = label_of.get(src)
            dst_label = label_of.get(dst)
            if not src_label or not dst_label:
                continue
            combos[(src_label, rel, dst_label)].append({"src": src, "dst": dst})

        for (src_label, rel, dst_label), rows in combos.items():
            session.run(
                f"""
                UNWIND $rows AS r
                MATCH (s:{src_label} {{attack_id: r.src}})
                MATCH (d:{dst_label} {{attack_id: r.dst}})
                MERGE (s)-[:{rel}]->(d)
                """,
                rows=rows,
            )

        # --- Meta singleton ----------------------------------------------
        session.run(
            """
            MERGE (m:AttackMeta {id: $id})
            SET m.version = $version, m.tactics = $tactics, m.techniques = $techniques,
                m.groups = $groups, m.software = $software, m.mitigations = $mitigations,
                m.ingested_at = $now
            """,
            id=_META_ID, version=version, tactics=len(parsed.tactics),
            techniques=len(parsed.techniques), groups=len(parsed.groups),
            software=len(parsed.software), mitigations=len(parsed.mitigations), now=now,
        )

    return {
        "tactics": len(parsed.tactics),
        "techniques": len(parsed.techniques),
        "groups": len(parsed.groups),
        "software": len(parsed.software),
        "mitigations": len(parsed.mitigations),
    }


def attack_status(driver: Driver) -> dict:
    """Whether ATT&CK is ingested, at what version, with live node counts."""
    with driver.session() as session:
        meta = session.run("MATCH (m:AttackMeta {id: $id}) RETURN m.version AS version", id=_META_ID).single()
        counts = {}
        for label, key in _COUNT_LABELS:
            rec = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
            counts[key] = rec["c"] if rec else 0
    return {
        "ingested": meta is not None,
        "version": meta["version"] if meta else None,
        "counts": counts,
    }


def _observed_counts(session, project_id: str) -> dict[str, int]:
    """attack_id -> number of the project's TTP entities mapped directly to it."""
    result = session.run(
        """
        MATCH (t:TTP {project_id: $pid})-[:MAPS_TO]->(tech:AttackTechnique)
        RETURN tech.attack_id AS tid, count(DISTINCT t) AS c
        """,
        pid=project_id,
    )
    return {row["tid"]: row["c"] for row in result}


def get_matrix(driver: Driver, project_id: str) -> dict:
    """Full tactic → technique model with per-technique observed coverage.

    A top-level technique's ``observed_count`` includes its sub-techniques'
    counts. Tactics are ordered by ``attack_id`` (TA0001 → …), which the design
    spec adopts as the canonical column order.
    """
    with driver.session() as session:
        meta = session.run(
            "MATCH (m:AttackMeta {id: $id}) RETURN m.version AS version", id=_META_ID
        ).single()
        counts = _observed_counts(session, project_id)
        tactics = session.run(
            """
            MATCH (ta:AttackTactic)
            RETURN ta.attack_id AS id, ta.name AS name, ta.shortname AS shortname
            ORDER BY ta.attack_id
            """
        ).data()
        rows = session.run(
            """
            MATCH (tech:AttackTechnique)-[:PART_OF_TACTIC]->(ta:AttackTactic)
            WHERE tech.is_subtechnique = false
            OPTIONAL MATCH (sub:AttackTechnique)-[:SUBTECHNIQUE_OF]->(tech)
            RETURN ta.attack_id AS tactic_id, tech.attack_id AS id, tech.name AS name,
                   collect(DISTINCT {id: sub.attack_id, name: sub.name}) AS subs
            ORDER BY tech.attack_id
            """
        ).data()

    by_tactic: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        direct = counts.get(row["id"], 0)
        subs_out = []
        total = direct
        for sub in row["subs"]:
            if not sub.get("id"):
                continue  # OPTIONAL MATCH placeholder when a technique has no subs
            sub_count = counts.get(sub["id"], 0)
            total += sub_count
            subs_out.append({"id": sub["id"], "name": sub["name"], "observed_count": sub_count})
        subs_out.sort(key=lambda s: s["id"])
        by_tactic[row["tactic_id"]].append({
            "id": row["id"],
            "name": row["name"],
            "is_subtechnique": False,
            "observed_count": total,
            "subtechniques": subs_out,
        })

    tactics_out = [
        {
            "id": ta["id"],
            "name": ta["name"],
            "shortname": ta["shortname"],
            "techniques": by_tactic.get(ta["id"], []),
        }
        for ta in tactics
    ]
    return {
        "version": meta["version"] if meta else None,
        "ingested": meta is not None,
        "tactics": tactics_out,
    }


def get_technique(driver: Driver, tid: str, project_id: str) -> dict | None:
    """Detail for one technique: tactics, platforms, detection, mitigations,
    groups that use it, and this project's entities mapped to it."""
    with driver.session() as session:
        record = session.run(
            """
            MATCH (tech:AttackTechnique {attack_id: $tid})
            OPTIONAL MATCH (tech)-[:PART_OF_TACTIC]->(ta:AttackTactic)
            OPTIONAL MATCH (tech)-[:SUBTECHNIQUE_OF]->(parent:AttackTechnique)
            OPTIONAL MATCH (m:AttackMitigation)-[:MITIGATES]->(tech)
            OPTIONAL MATCH (g:AttackGroup)-[:USES]->(tech)
            OPTIONAL MATCH (e {project_id: $pid})-[:MAPS_TO]->(tech)
            RETURN tech,
                   parent.attack_id AS parent_id,
                   collect(DISTINCT {id: ta.attack_id, name: ta.name, shortname: ta.shortname}) AS tactics,
                   collect(DISTINCT {id: m.attack_id, name: m.name}) AS mitigations,
                   collect(DISTINCT {id: g.attack_id, name: g.name}) AS groups,
                   collect(DISTINCT {id: e.id, name: e.name, entity_type: e.entity_type}) AS related
            """,
            tid=tid, pid=project_id,
        ).single()

    if not record or record["tech"] is None:
        return None

    tech = dict(record["tech"])

    def _clean(items, key="id"):
        return [it for it in items if it.get(key)]

    return {
        "id": tech.get("attack_id"),
        "name": tech.get("name", ""),
        "description": tech.get("description", ""),
        "is_subtechnique": bool(tech.get("is_subtechnique", False)),
        "parent_id": record["parent_id"],
        "tactics": _clean(record["tactics"]),
        "platforms": list(tech.get("platforms", []) or []),
        "detection": tech.get("detection", "") or "",
        "mitigations": _clean(record["mitigations"]),
        "groups": _clean(record["groups"]),
        "related_entities": _clean(record["related"]),
    }


def resolve_ttps(driver: Driver, project_id: str) -> dict:
    """Link this project's TTP/ThreatActor entities to canonical ATT&CK nodes.

    - ``TTP`` name → technique-id regex → ``MAPS_TO`` the matching ``AttackTechnique``.
    - ``ThreatActor`` name → G-code regex, else an exact (case-insensitive) name /
      alias match → ``MAPS_TO`` the matching ``AttackGroup``.

    Idempotent (``MERGE``). Returns ``{"mapped": <entities linked>}``.
    """
    mapped = 0
    with driver.session() as session:
        ttps = session.run(
            "MATCH (t:TTP {project_id: $pid}) RETURN t.id AS id, t.name AS name",
            pid=project_id,
        ).data()
        for ttp in ttps:
            match = _TECH_RE.search(ttp.get("name") or "")
            if not match:
                continue
            rec = session.run(
                """
                MATCH (t:TTP {id: $id})
                MATCH (tech:AttackTechnique {attack_id: $code})
                MERGE (t)-[:MAPS_TO]->(tech)
                RETURN count(*) AS c
                """,
                id=ttp["id"], code=match.group(0),
            ).single()
            if rec and rec["c"] > 0:
                mapped += 1

        actors = session.run(
            "MATCH (a:ThreatActor {project_id: $pid}) RETURN a.id AS id, a.name AS name",
            pid=project_id,
        ).data()
        for actor in actors:
            name = actor.get("name") or ""
            gmatch = _GROUP_RE.search(name)
            linked = False
            if gmatch:
                rec = session.run(
                    """
                    MATCH (a:ThreatActor {id: $id})
                    MATCH (g:AttackGroup {attack_id: $code})
                    MERGE (a)-[:MAPS_TO]->(g)
                    RETURN count(*) AS c
                    """,
                    id=actor["id"], code=gmatch.group(0),
                ).single()
                linked = bool(rec and rec["c"] > 0)
            if not linked:
                rec = session.run(
                    """
                    MATCH (a:ThreatActor {id: $id})
                    MATCH (g:AttackGroup)
                    WHERE toLower(g.name) = toLower($name)
                       OR any(al IN g.aliases WHERE toLower(al) = toLower($name))
                    MERGE (a)-[:MAPS_TO]->(g)
                    RETURN count(*) AS c
                    """,
                    id=actor["id"], name=name,
                ).single()
                linked = bool(rec and rec["c"] > 0)
            if linked:
                mapped += 1

    return {"mapped": mapped}


def navigator_layer(driver: Driver, project_id: str) -> dict:
    """Build a MITRE ATT&CK Navigator **layer v4.5** JSON scored by observed count.

    Each technique with observed coverage is emitted once per tactic it belongs
    to (Navigator places entries by ``tactic``). Gradient runs white → red.
    """
    with driver.session() as session:
        meta = session.run(
            "MATCH (m:AttackMeta {id: $id}) RETURN m.version AS version", id=_META_ID
        ).single()
        rows = session.run(
            """
            MATCH (t:TTP {project_id: $pid})-[:MAPS_TO]->(tech:AttackTechnique)
            WITH tech, count(DISTINCT t) AS score
            OPTIONAL MATCH (tech)-[:PART_OF_TACTIC]->(ta:AttackTactic)
            RETURN tech.attack_id AS id, score, collect(ta.shortname) AS tactics
            """,
            pid=project_id,
        ).data()

    version = meta["version"] if meta else ""
    attack_major = (version.split(".")[0] if version else "19") or "19"

    techniques = []
    max_score = 0
    for row in rows:
        score = row["score"]
        max_score = max(max_score, score)
        tactic_names = [sn for sn in row["tactics"] if sn] or [None]
        for shortname in tactic_names:
            entry = {
                "techniqueID": row["id"],
                "score": score,
                "color": "",
                "comment": f"{score} observed TTP mapping(s)",
                "enabled": True,
            }
            if shortname:
                entry["tactic"] = shortname
            techniques.append(entry)

    return {
        "name": f"Observed coverage — {project_id[:8]}",
        "versions": {"layer": "4.5", "navigator": "4.9.0", "attack": attack_major},
        "domain": "enterprise-attack",
        "description": "Project TTP coverage mapped to MITRE ATT&CK, scored by observed count.",
        "techniques": techniques,
        "gradient": {
            "colors": ["#ffffff", "#ff6666"],
            "minValue": 0,
            "maxValue": max_score if max_score > 0 else 1,
        },
        "legendItems": [],
        "showTacticRowBackground": False,
        "hideDisabled": False,
    }
