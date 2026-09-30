import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/entity-types")
def get_entity_type_hierarchy():
    """Get the entity type hierarchy."""
    from intel_platform.models.type_hierarchy import TYPE_HIERARCHY
    return {
        "hierarchy": TYPE_HIERARCHY,
        "categories": list(TYPE_HIERARCHY.keys()),
    }


@router.get("/entities")
def search_entities(
    response: Response,
    project_id: str, query: str = "", entity_type: str | None = None,
    limit: int = Query(50, ge=1, le=10000), offset: int = Query(0, ge=0),
    store: GraphStore = Depends(get_graph_store),
):
    """Entities matching the filters, capped at `limit`.

    `X-Total-Count` reports how many match in full, so a caller can tell a
    complete list from a truncated one. Nothing said so before, and every
    consumer takes the default 50: the geo map plotted 50 of 398 locations and
    the network sidebar grouped 50 of 5,486 entities under type headings that
    read as totals. A header keeps the body a bare list, which every existing
    caller already parses as one.
    """
    results = store.search_entities(
        project_id=project_id, query=query, entity_type=entity_type,
        limit=limit, offset=offset,
    )
    total = store.count_entities(project_id=project_id, query=query, entity_type=entity_type)
    response.headers["X-Total-Count"] = str(total)
    # Browsers hide non-safelisted headers from cross-origin JS unless exposed,
    # and the analyst UI is served from a different origin in development.
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return results


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, store: GraphStore = Depends(get_graph_store)):
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    relationships = store.get_relationships(entity_id)
    return {"entity": entity, "relationships": relationships}


_NO_SCOPE = (
    "project_id is required: this entity belongs to no project (a shared catalog "
    "entry such as an ATT&CK technique), and an unscoped walk crosses into every project"
)


def _traversal_scope(requested: str | None, *entities: dict | None) -> str | None:
    """The project a traversal is confined to: the caller's, else the entities'.

    ATT&CK/CWE catalog nodes are shared by every project, so an unscoped walk
    through one reaches other projects' entities (and, through GraphRAG, their
    documents). The store confines a scoped walk; this picks the scope.
    """
    if requested:
        return requested
    for entity in entities:
        if entity and entity.get("project_id"):
            return entity["project_id"]
    return None


@router.get("/subgraph/{entity_id}")
def get_subgraph(
    entity_id: str,
    hops: int = Query(1, ge=1, le=4),
    project_id: str | None = None,
    store: GraphStore = Depends(get_graph_store),
):
    entity = store.get_entity(entity_id)
    if not entity:
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
    scope = _traversal_scope(project_id, entity)
    if not scope:
        raise HTTPException(status_code=400, detail=_NO_SCOPE)
    return store.get_subgraph(entity_id, hops=hops, project_id=scope)


@router.get("/paths/{entity_id_1}/{entity_id_2}")
def find_shortest_path(
    entity_id_1: str,
    entity_id_2: str,
    project_id: str | None = None,
    store: GraphStore = Depends(get_graph_store),
):
    scope = _traversal_scope(project_id, store.get_entity(entity_id_1), store.get_entity(entity_id_2))
    if not scope:
        raise HTTPException(status_code=400, detail=_NO_SCOPE)
    return store.find_shortest_path(entity_id_1, entity_id_2, project_id=scope)


class MergeEntitiesRequest(BaseModel):
    primary_id: str
    merge_ids: list[str]
    project_id: str


# Keys `get_relationships` adds about the endpoints; everything else on a
# relationship row is a property of the edge itself.
_REL_ENDPOINT_KEYS = frozenset({"rel_type", "source_id", "target_id", "source_name", "target_name", "direction"})
# A relationship type as Neo4j stores it. Checked before a type read from the
# graph is handed to APOC, although it came from the graph and not a request.
_REL_TYPE_SHAPE = re.compile(r"[A-Z][A-Z0-9_]*")


def _copy_edge_verbatim(store: GraphStore, rel_type: str, props: dict, source_id: str, target_id: str) -> bool:
    """Recreate an edge with its exact type and properties. False if nothing was created."""
    if not _REL_TYPE_SHAPE.fullmatch(rel_type or ""):
        return False
    with store._driver.session() as session:
        record = session.run(
            """
            MATCH (a {id: $source_id})
            MATCH (b {id: $target_id})
            CALL apoc.create.relationship(a, $rel_type, $props, b) YIELD rel
            RETURN count(rel) AS created
            """,
            source_id=source_id, target_id=target_id, rel_type=rel_type,
            props=store._serialize_props(props),
        ).single()
    return bool(record and record["created"])


def _transfer_edge(store: GraphStore, rel: dict, source_id: str, target_id: str, project_id: str) -> bool:
    """Recreate one edge between new endpoints, keeping its type and properties.

    Allowlisted types go through `create_relationship`, so an edge the primary
    already has is corroborated rather than duplicated. Types outside that
    allowlist — the ATT&CK/CWE catalog edges (MAPS_TO, HAS_WEAKNESS, ENABLES) —
    are copied verbatim: the allowlist guards types arriving from requests and
    model output, and this type is already in the graph. A property the model
    will not accept also falls back to the verbatim copy, so a merge is never
    refused over one odd value.
    """
    from pydantic import ValidationError

    from intel_platform.models.relationships import Relationship

    rel_type = rel.get("rel_type", "")
    props = {k: v for k, v in rel.items() if k not in _REL_ENDPOINT_KEYS}
    if rel_type in store.VALID_REL_TYPES:
        fields = {k: v for k, v in props.items() if k in Relationship.model_fields}
        try:
            created = store.create_relationship(Relationship(
                source_id=source_id, target_id=target_id, rel_type=rel_type,
                project_id=project_id, **fields,
            ))
            if created:
                return True
        except (ValueError, ValidationError):
            logger.warning("Merge: %s edge did not fit the model; copying it verbatim", rel_type, exc_info=True)
    try:
        return _copy_edge_verbatim(store, rel_type, props, source_id, target_id)
    except Exception:
        logger.exception("Merge: could not recreate a %s edge %s -> %s", rel_type, source_id, target_id)
        return False


@router.post("/entities/merge")
def merge_entities(req: MergeEntitiesRequest, store: GraphStore = Depends(get_graph_store)):
    """Merge entities into the primary, moving every edge as it was.

    Each edge keeps its direction, type and properties (evidence, provenance,
    polarity). An entity is deleted only once every one of its edges has been
    recreated on the primary; otherwise it is kept, and the response says so —
    deleting it anyway is how edges used to disappear behind a success message.
    """
    primary = store.get_entity(req.primary_id)
    if not primary:
        raise HTTPException(status_code=404, detail="Primary entity not found")

    merge_set = {mid for mid in req.merge_ids if mid != req.primary_id}
    merged_count = 0
    relationships_transferred = 0
    dropped_edges = 0
    not_merged: list[str] = []
    not_found: list[str] = []

    for merge_id in req.merge_ids:
        if merge_id == req.primary_id:
            continue
        if not store.get_entity(merge_id):
            not_found.append(merge_id)
            continue

        failed = 0
        for rel in store.get_relationships(merge_id):
            if "direction" in rel:
                outgoing = rel["direction"] == "out"
            else:
                outgoing = rel.get("source_id") == merge_id
            other = rel.get("target_id") if outgoing else rel.get("source_id")
            # An edge to the primary, or to another entity being merged into it,
            # would become a self-loop on the primary.
            if other == req.primary_id or other in merge_set:
                continue
            source_id, target_id = (req.primary_id, other) if outgoing else (other, req.primary_id)
            if _transfer_edge(store, rel, source_id, target_id, req.project_id):
                relationships_transferred += 1
            else:
                failed += 1

        if failed:
            dropped_edges += failed
            not_merged.append(merge_id)
            logger.warning("Merge: kept %s; %d of its edges could not be moved", merge_id, failed)
            continue
        store.delete_entity(merge_id)
        merged_count += 1

    return {
        "primary_id": req.primary_id,
        "primary_name": primary.get("name"),
        "entities_merged": merged_count,
        "relationships_transferred": relationships_transferred,
        "dropped_edges": dropped_edges,
        "entities_not_merged": not_merged,
        "entities_not_found": not_found,
        "complete": not not_merged and not not_found,
    }


class UpdateEntityTypeRequest(BaseModel):
    entity_type: str


@router.put("/entities/{entity_id}/type")
def update_entity_type(entity_id: str, req: UpdateEntityTypeRequest, store: GraphStore = Depends(get_graph_store)):
    """Update an entity's type (e.g., fix a misclassification)."""
    # SECURITY: validate against known entity types to prevent arbitrary values
    from intel_platform.models.entities import EntityType
    valid_types = {e.value for e in EntityType}
    if req.entity_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {req.entity_type}")

    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # The type lives in three places — the label, entity_type and entity_category
    # — and each has readers (ATT&CK attribution and the map read the label and
    # the category, the panel reads entity_type), so all three move together.
    # Only the old type label is swapped: other labels, such as the shared
    # :Entity label, stay. The labels are validated by the same rule the store
    # creates them with.
    from intel_platform.graph.store import _validate_label
    from intel_platform.models.type_hierarchy import normalize_entity_type

    _, new_category = normalize_entity_type(req.entity_type)
    new_label = _validate_label(req.entity_type)
    old_label = _validate_label(entity.get("entity_type") or "")
    remove = [old_label] if old_label not in (new_label, "Entity") else []
    with store._driver.session() as session:
        session.run(
            """
            MATCH (n {id: $id})
            CALL apoc.create.removeLabels(n, $remove) YIELD node
            WITH node
            CALL apoc.create.addLabels(node, [$new_label]) YIELD node AS retyped
            SET retyped.entity_type = $new_type, retyped.entity_category = $new_category
            """,
            id=entity_id, remove=remove, new_label=new_label,
            new_type=req.entity_type, new_category=new_category,
        )
    if entity.get("project_id"):
        from intel_platform.services.graph_cache import graph_cache
        graph_cache.invalidate(entity["project_id"])

    return {
        "id": entity_id,
        "name": entity.get("name"),
        "old_type": entity.get("entity_type"),
        "new_type": req.entity_type,
    }
