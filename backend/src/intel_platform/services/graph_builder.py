from __future__ import annotations

import jellyfish

from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import (
    Person, Organization, Location, Event, IPAddress, Domain, Hash,
    Vulnerability, TTP, Malware, ThreatActor, Campaign,
)
from intel_platform.models.relationships import Relationship

ENTITY_TYPE_MAP = {
    "Person": Person, "Organization": Organization, "Location": Location,
    "Event": Event, "IPAddress": IPAddress, "Domain": Domain, "Hash": Hash,
    "Vulnerability": Vulnerability, "TTP": TTP, "Malware": Malware,
    "ThreatActor": ThreatActor, "Campaign": Campaign,
}


def resolve_entity_name(name: str, existing_names: list[str], threshold: float = 0.85) -> str | None:
    """Resolve entity name using Jaro-Winkler similarity. Threshold is 0.0-1.0."""
    if not existing_names:
        return None
    best_match = None
    best_score = 0.0
    for existing in existing_names:
        score = jellyfish.jaro_winkler_similarity(name.lower(), existing.lower())
        if score > best_score:
            best_score = score
            best_match = existing
    if best_score >= threshold:
        return best_match
    return None


def build_graph_from_extractions(
    store: GraphStore, entities: list[dict], relationships: list[dict], project_id: str,
) -> dict:
    created = 0
    merged = 0
    name_to_id: dict[str, str] = {}

    existing = store.search_entities(project_id=project_id, limit=10000)
    existing_names = [e["name"] for e in existing]
    existing_name_to_id = {e["name"]: e["id"] for e in existing}

    for ent_data in entities:
        name = ent_data["name"]
        entity_type = ent_data["entity_type"]

        match = resolve_entity_name(name, existing_names, threshold=0.93)
        if match:
            name_to_id[name] = existing_name_to_id[match]
            merged += 1
            continue

        cls = ENTITY_TYPE_MAP.get(entity_type)
        if not cls:
            continue

        entity = cls(name=name, project_id=project_id)
        store.create_entity(entity)
        name_to_id[name] = entity.id
        existing_names.append(name)
        existing_name_to_id[name] = entity.id
        created += 1

    rels_created = 0
    for rel_data in relationships:
        source_id = name_to_id.get(rel_data["source_name"])
        target_id = name_to_id.get(rel_data["target_name"])
        if not source_id or not target_id:
            continue
        rel = Relationship(
            source_id=source_id, target_id=target_id,
            rel_type=rel_data["rel_type"],
            confidence=rel_data.get("confidence", 0.5),
            source=rel_data.get("source", ""), method=rel_data.get("method", ""),
        )
        store.create_relationship(rel)
        rels_created += 1

    return {"entities_created": created, "entities_merged": merged, "relationships_created": rels_created}
