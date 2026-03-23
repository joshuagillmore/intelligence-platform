from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

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
    project_id: str, query: str = "", entity_type: str | None = None,
    limit: int = 50, offset: int = 0,
    store: GraphStore = Depends(get_graph_store),
):
    return store.search_entities(
        project_id=project_id, query=query, entity_type=entity_type,
        limit=limit, offset=offset,
    )


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, store: GraphStore = Depends(get_graph_store)):
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    relationships = store.get_relationships(entity_id)
    return {"entity": entity, "relationships": relationships}


@router.get("/subgraph/{entity_id}")
def get_subgraph(entity_id: str, hops: int = Query(1, ge=1, le=5), store: GraphStore = Depends(get_graph_store)):
    return store.get_subgraph(entity_id, hops=hops)


@router.get("/paths/{entity_id_1}/{entity_id_2}")
def find_shortest_path(entity_id_1: str, entity_id_2: str, store: GraphStore = Depends(get_graph_store)):
    return store.find_shortest_path(entity_id_1, entity_id_2)


class MergeEntitiesRequest(BaseModel):
    primary_id: str
    merge_ids: list[str]
    project_id: str


@router.post("/entities/merge")
def merge_entities(req: MergeEntitiesRequest, store: GraphStore = Depends(get_graph_store)):
    """Merge multiple entities into one. Relationships are transferred to the primary entity."""
    primary = store.get_entity(req.primary_id)
    if not primary:
        raise HTTPException(status_code=404, detail="Primary entity not found")

    merged_count = 0
    relationships_transferred = 0

    for merge_id in req.merge_ids:
        if merge_id == req.primary_id:
            continue
        merge_entity = store.get_entity(merge_id)
        if not merge_entity:
            continue

        # Transfer all relationships from merge_entity to primary
        rels = store.get_relationships(merge_id)
        for rel in rels:
            target_id = rel.get("target_id", "")
            if target_id == req.primary_id:
                continue  # Skip self-referencing
            from intel_platform.models.relationships import Relationship
            try:
                new_rel = Relationship(
                    source_id=req.primary_id,
                    target_id=target_id,
                    rel_type=rel.get("rel_type", "ASSOCIATED_WITH"),
                    confidence=float(rel.get("confidence", rel.get("props", {}).get("confidence", 0.5))),
                    source=rel.get("source", rel.get("props", {}).get("source", "")),
                    method="merge",
                )
                store.create_relationship(new_rel)
                relationships_transferred += 1
            except ValueError:
                pass

        # Delete the merged entity
        store.delete_entity(merge_id)
        merged_count += 1

    return {
        "primary_id": req.primary_id,
        "primary_name": primary.get("name"),
        "entities_merged": merged_count,
        "relationships_transferred": relationships_transferred,
    }


class UpdateEntityTypeRequest(BaseModel):
    entity_type: str


@router.put("/entities/{entity_id}/type")
def update_entity_type(entity_id: str, req: UpdateEntityTypeRequest, store: GraphStore = Depends(get_graph_store)):
    """Update an entity's type (e.g., fix a misclassification)."""
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Update the entity_type property
    with store._driver.session() as session:
        session.run(
            "MATCH (n {id: $id}) SET n.entity_type = $new_type",
            id=entity_id,
            new_type=req.entity_type,
        )

    return {
        "id": entity_id,
        "name": entity.get("name"),
        "old_type": entity.get("entity_type"),
        "new_type": req.entity_type,
    }
