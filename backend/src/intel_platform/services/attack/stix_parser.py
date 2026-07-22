"""Pure STIX 2.1 → ATT&CK model parser.

No I/O: takes the already-loaded bundle dict and returns a :class:`ParsedAttack`.
This is the core of the subsystem and is tested exhaustively against a synthetic
bundle (``tests/test_attack_parser.py``); ``graph_ops.ingest_model`` consumes the
result.

Parsing rules (from the design spec):

- The **ATT&CK ID is never the STIX ``id``** — it is
  ``external_references[source_name == "mitre-attack"].external_id``.
- Objects with ``revoked`` or ``x_mitre_deprecated`` true are skipped, and any
  relationship whose endpoints were skipped is dropped with them.
- Technique → Tactic is derived from ``kill_chain_phases`` (``phase_name`` matched
  to a tactic ``shortname``), not from a relationship object.
- Only ``subtechnique-of`` / ``uses`` / ``mitigates`` relationships are kept for
  Phase 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# STIX relationship_type -> canonical graph edge type (Phase 1 only).
_REL_MAP = {
    "subtechnique-of": "SUBTECHNIQUE_OF",
    "uses": "USES",
    "mitigates": "MITIGATES",
}


@dataclass
class ParsedAttack:
    """The parsed, load-ready ATT&CK model — plain dicts, no STIX ids."""

    tactics: list[dict] = field(default_factory=list)
    techniques: list[dict] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)
    software: list[dict] = field(default_factory=list)
    mitigations: list[dict] = field(default_factory=list)
    # (src_attack_id, "USES"|"MITIGATES"|"SUBTECHNIQUE_OF", dst_attack_id)
    relationships: list[tuple[str, str, str]] = field(default_factory=list)


def attack_id(obj: dict) -> str | None:
    """Return the ATT&CK external id (T1566, TA0001, G0007, ...) or None."""
    for ref in obj.get("external_references", []) or []:
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def _is_filtered(obj: dict) -> bool:
    """True when the object is revoked or deprecated and must be excluded."""
    return bool(obj.get("revoked")) or bool(obj.get("x_mitre_deprecated"))


def _kept_tactic_shortnames(obj: dict) -> list[str]:
    """The mitre-attack kill-chain phase names (tactic shortnames) for a technique."""
    names: list[str] = []
    for phase in obj.get("kill_chain_phases", []) or []:
        if phase.get("kill_chain_name") == "mitre-attack" and phase.get("phase_name"):
            names.append(phase["phase_name"])
    return names


def parse_bundle(bundle: dict) -> ParsedAttack:
    """Parse a STIX 2.1 Enterprise bundle into a :class:`ParsedAttack`.

    Two linear passes over the flat ``objects`` array: pass 1 builds the nodes
    (and a ``{stix_id: attack_id}`` map for the kept objects); pass 2 resolves
    relationships through that map, dropping any edge whose endpoint was filtered.
    """
    objects = bundle.get("objects", []) or []
    parsed = ParsedAttack()
    stix_to_attack: dict[str, str] = {}

    # --- Pass 1: nodes -----------------------------------------------------
    for obj in objects:
        obj_type = obj.get("type")
        if obj_type == "relationship":
            continue
        if _is_filtered(obj):
            continue
        aid = attack_id(obj)
        if not aid:
            continue
        stix_id = obj.get("id")

        if obj_type == "x-mitre-tactic":
            parsed.tactics.append({
                "attack_id": aid,
                "name": obj.get("name", ""),
                "shortname": obj.get("x_mitre_shortname", ""),
                "description": obj.get("description", ""),
            })
        elif obj_type == "attack-pattern":
            parsed.techniques.append({
                "attack_id": aid,
                "name": obj.get("name", ""),
                "description": obj.get("description", ""),
                "is_subtechnique": bool(obj.get("x_mitre_is_subtechnique", False)),
                "platforms": list(obj.get("x_mitre_platforms", []) or []),
                "detection": obj.get("x_mitre_detection", "") or "",
                "tactic_shortnames": _kept_tactic_shortnames(obj),
            })
        elif obj_type == "intrusion-set":
            parsed.groups.append({
                "attack_id": aid,
                "name": obj.get("name", ""),
                "aliases": list(obj.get("aliases", []) or []),
                "description": obj.get("description", ""),
            })
        elif obj_type in ("malware", "tool"):
            parsed.software.append({
                "attack_id": aid,
                "name": obj.get("name", ""),
                "software_type": "malware" if obj_type == "malware" else "tool",
                "platforms": list(obj.get("x_mitre_platforms", []) or []),
                "description": obj.get("description", ""),
            })
        elif obj_type == "course-of-action":
            parsed.mitigations.append({
                "attack_id": aid,
                "name": obj.get("name", ""),
                "description": obj.get("description", ""),
            })
        else:
            continue  # object type not part of the Phase-1 model

        if stix_id:
            stix_to_attack[stix_id] = aid

    # --- Pass 2: relationships --------------------------------------------
    for obj in objects:
        if obj.get("type") != "relationship" or _is_filtered(obj):
            continue
        mapped = _REL_MAP.get(obj.get("relationship_type"))
        if not mapped:
            continue
        src = stix_to_attack.get(obj.get("source_ref"))
        dst = stix_to_attack.get(obj.get("target_ref"))
        if not src or not dst:
            continue  # an endpoint was filtered out (revoked/deprecated/unknown)
        parsed.relationships.append((src, mapped, dst))

    return parsed
