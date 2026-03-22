from __future__ import annotations

import jellyfish

from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import (
    Person, Organization, Location, Event, IPAddress, Domain, Hash,
    Vulnerability, TTP, Malware, ThreatActor, Campaign,
)
from intel_platform.models.relationships import Relationship
from intel_platform.models.type_hierarchy import normalize_entity_type

ENTITY_TYPE_MAP = {
    "Person": Person, "Organization": Organization, "Location": Location,
    "Event": Event, "IPAddress": IPAddress, "Domain": Domain, "Hash": Hash,
    "Vulnerability": Vulnerability, "TTP": TTP, "Malware": Malware,
    "ThreatActor": ThreatActor, "Campaign": Campaign,
}


def resolve_entity_name(
    name: str, existing_names: list[str], threshold: float = 0.92,
    entity_type: str = "", existing_types: dict[str, str] | None = None,
) -> str | None:
    """Resolve entity name using Jaro-Winkler similarity + substring matching.

    Only merges entities of compatible types when type info is available.
    Cyber entities (IP, Domain, Hash, CVE, TTP) require exact match only.
    """
    if not existing_names:
        return None

    # Cyber entity types should ONLY match exactly (no fuzzy matching)
    EXACT_MATCH_TYPES = {"IPAddress", "Domain", "Hash", "Vulnerability", "TTP"}
    if entity_type in EXACT_MATCH_TYPES:
        name_lower = name.lower().strip()
        for existing in existing_names:
            if existing.lower().strip() == name_lower:
                return existing
        return None

    best_match = None
    best_score = 0.0
    name_lower = name.lower().strip()

    for existing in existing_names:
        existing_lower = existing.lower().strip()

        # Skip type-incompatible entities if type info available
        if existing_types and entity_type:
            existing_type = existing_types.get(existing, "")
            if existing_type in EXACT_MATCH_TYPES or entity_type in EXACT_MATCH_TYPES:
                continue  # Don't fuzzy-match cyber entities

        # Exact match
        if name_lower == existing_lower:
            return existing

        # Jaro-Winkler similarity
        score = jellyfish.jaro_winkler_similarity(name_lower, existing_lower)
        if score > best_score:
            best_score = score
            best_match = existing

    if best_score >= threshold:
        return best_match

    # Fallback: substring matching for partial names (Person names only)
    # "Putin" should match "Vladimir Putin"
    if entity_type in ("Person", "ThreatActor", ""):
        import re as _re
        for existing in existing_names:
            existing_lower = existing.lower().strip()
            # Skip cyber entities
            if existing_types and existing_types.get(existing, "") in EXACT_MATCH_TYPES:
                continue
            shorter = min(name_lower, existing_lower, key=len)
            longer = max(name_lower, existing_lower, key=len)
            if len(shorter) >= 4 and _re.search(r'\b' + _re.escape(shorter) + r'\b', longer) and len(shorter) / len(longer) > 0.3:
                return existing

    return None


def build_graph_from_extractions(
    store: GraphStore, entities: list[dict], relationships: list[dict], project_id: str,
    source_doc_id: str = "",
) -> dict:
    from intel_platform.config import settings

    created = 0
    merged = 0
    name_to_id: dict[str, str] = {}
    resolution_threshold = settings.entity_resolution_threshold

    # Cache for resolved names within this batch to avoid repeated lookups
    _resolution_cache: dict[str, str | None] = {}
    # Track newly created entities for intra-batch resolution
    batch_names: list[str] = []
    batch_name_to_id: dict[str, str] = {}
    batch_name_to_type: dict[str, str] = {}

    for ent_data in entities:
        name = ent_data["name"]
        raw_type = ent_data["entity_type"]

        # Check intra-batch cache first
        cache_key = f"{name}::{raw_type}"
        if cache_key in _resolution_cache:
            cached = _resolution_cache[cache_key]
            if cached:
                name_to_id[name] = cached
                merged += 1
                continue

        # Try resolution against entities created in this batch
        match = resolve_entity_name(
            name, batch_names, threshold=resolution_threshold,
            entity_type=raw_type, existing_types=batch_name_to_type,
        )
        if match:
            name_to_id[name] = batch_name_to_id[match]
            _resolution_cache[cache_key] = batch_name_to_id[match]
            merged += 1
            continue

        # Use indexed lookup against the graph (instead of loading all entities)
        candidates = store.search_entity_by_name(project_id, name, limit=20)
        if candidates:
            candidate_names = [c["name"] for c in candidates]
            candidate_name_to_id = {c["name"]: c["id"] for c in candidates}
            candidate_name_to_type = {c["name"]: c.get("entity_type", "") for c in candidates}
            match = resolve_entity_name(
                name, candidate_names, threshold=resolution_threshold,
                entity_type=raw_type, existing_types=candidate_name_to_type,
            )
            if match:
                name_to_id[name] = candidate_name_to_id[match]
                _resolution_cache[cache_key] = candidate_name_to_id[match]
                merged += 1
                continue

        _resolution_cache[cache_key] = None

        # Normalize the entity type using the hierarchy
        specific_type, parent_category = normalize_entity_type(raw_type)

        # Try to find a Pydantic class for the specific type, then parent category
        cls = ENTITY_TYPE_MAP.get(specific_type) or ENTITY_TYPE_MAP.get(parent_category)
        # Determine source doc ID from extraction data or caller
        entity_doc_id = ent_data.get("source", "") or source_doc_id

        # Build constructor kwargs, passing through extracted attributes
        kwargs: dict = {"name": name, "project_id": project_id, "source_doc_id": entity_doc_id}
        attrs = ent_data.get("attributes", {})
        if attrs and cls:
            # Only pass attributes that the Pydantic model accepts
            model_fields = set(cls.model_fields.keys())
            for k, v in attrs.items():
                if k in model_fields and v:
                    kwargs[k] = v

        if cls:
            entity = cls(**kwargs)
        else:
            # Generic entity for unknown types
            from intel_platform.models.entities import Entity, EntityType
            try:
                et = EntityType(specific_type)
            except ValueError:
                et = EntityType.CUSTOM
            entity = Entity(name=name, entity_type=et, project_id=project_id, source_doc_id=entity_doc_id)

        store.create_entity(entity)
        name_to_id[name] = entity.id
        batch_names.append(name)
        batch_name_to_id[name] = entity.id
        batch_name_to_type[name] = raw_type
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
