import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.evidence import find_passages
from intel_platform.graph.merge import copy_edge_verbatim, merge_entity_into, transfer_edge
from intel_platform.graph.store import GraphStore
from intel_platform.models.responses import (
    EntityDetailResponse,
    EntityMergeResponse,
    EntityProperties,
    EntityTypeChangedResponse,
    EntityTypeHierarchyResponse,
    ShortestPathResponse,
    SubgraphResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/entity-types", response_model=EntityTypeHierarchyResponse)
def get_entity_type_hierarchy():
    """Get the entity type hierarchy."""
    from intel_platform.models.type_hierarchy import TYPE_HIERARCHY
    return {
        "hierarchy": TYPE_HIERARCHY,
        "categories": list(TYPE_HIERARCHY.keys()),
    }


@router.get("/entities", response_model=list[EntityProperties], response_model_exclude_unset=True)
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


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse, response_model_exclude_unset=True)
def get_entity(entity_id: str, store: GraphStore = Depends(get_graph_store)):
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    relationships = store.get_relationships(entity_id)
    return {"entity": entity, "relationships": relationships}


# Evidence passages quoted per document in the evidence chain.
PASSAGES_PER_DOCUMENT = 3


class EvidencePassage(BaseModel):
    text: str
    # Character offset of the mention in the document's content.
    offset: int


class MentioningDocument(BaseModel):
    id: str
    name: str
    url: str
    source_doc_id: str
    # How many extracted mentions of the entity the document carries.
    mention_count: int
    passages: list[EvidencePassage]


class EntityDocumentsResponse(BaseModel):
    documents: list[MentioningDocument]
    count: int
    total: int


@router.get("/entities/{entity_id}/documents", response_model=EntityDocumentsResponse)
def get_entity_documents(
    entity_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    store: GraphStore = Depends(get_graph_store),
):
    """The documents that mention an entity, with evidence passages: its evidence chain.

    One call, from the entity's MENTIONS edges, in its own project; the
    network page used to request evidence document by document. Most-
    mentioning documents first. Each carries up to PASSAGES_PER_DOCUMENT
    passages around the entity's name — matched exactly first, then ignoring
    case, since reporting does not keep an extractor's capitalisation.
    `count` is this page, `total` every document that mentions the entity.
    """
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    rows, total = store.documents_mentioning(
        entity_id, entity.get("project_id") or "", limit=limit, offset=offset,
    )
    name = entity.get("name") or ""
    documents = []
    for row in rows:
        passages, _ = find_passages(row["content"], name, PASSAGES_PER_DOCUMENT)
        if not passages:
            passages, _ = find_passages(row["content"], name, PASSAGES_PER_DOCUMENT, ignore_case=True)
        documents.append({
            "id": row["id"],
            "name": row["name"] or "",
            "url": row["url"],
            "source_doc_id": row["source_doc_id"],
            "mention_count": int(row["mention_count"]),
            "passages": passages,
        })
    return {"documents": documents, "count": len(documents), "total": total}


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


@router.get("/subgraph/{entity_id}", response_model=SubgraphResponse, response_model_exclude_unset=True)
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


@router.get("/paths/{entity_id_1}/{entity_id_2}", response_model=ShortestPathResponse, response_model_exclude_unset=True)
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


# The edge-moving logic lives in graph.merge, shared with the startup backfill
# that merges entities found to share a name key. These names stay here because
# they are the route's seam: tests patch `_transfer_edge` on this module.
_copy_edge_verbatim = copy_edge_verbatim
_transfer_edge = transfer_edge


@router.post("/entities/merge", response_model=EntityMergeResponse)
def merge_entities(req: MergeEntitiesRequest, store: GraphStore = Depends(get_graph_store)):
    """Merge entities into the primary, moving every edge as it was.

    Each edge keeps its direction, type and properties (evidence, provenance,
    polarity), and the documents that mention a merged entity move to the
    primary. An entity is deleted only once every one of its edges has been
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

        # An edge to the primary, or to another entity being merged into it,
        # would become a self-loop on the primary, so those are skipped.
        outcome = merge_entity_into(
            store, req.primary_id, merge_id, project_id=req.project_id,
            skip_ids=merge_set, transfer=_transfer_edge,
        )
        relationships_transferred += outcome.transferred
        if not outcome.deleted:
            dropped_edges += outcome.failed
            not_merged.append(merge_id)
            continue
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


@router.put("/entities/{entity_id}/type", response_model=EntityTypeChangedResponse)
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
    from neo4j.exceptions import ConstraintError

    with store._driver.session() as session:
        try:
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
            ).consume()
        except ConstraintError:
            # The type is part of the entity's key: another entity of that
            # type with this name already exists in the project. Two nodes
            # for one entity is what the key forbids; the analyst merges them.
            logger.info("Retype of %s to %s refused: the name is taken for that type", entity_id, req.entity_type)
            raise HTTPException(
                status_code=409,
                detail=f"A {req.entity_type} with this name already exists in the project; merge the two instead",
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
