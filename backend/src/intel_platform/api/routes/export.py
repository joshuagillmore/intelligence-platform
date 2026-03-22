import uuid as uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])

# STIX entity type mapping
ENTITY_TO_STIX = {
    "Person": "identity",
    "Organization": "identity",
    "Location": "location",
    "ThreatActor": "threat-actor",
    "Malware": "malware",
    "Campaign": "campaign",
    "IPAddress": "ipv4-addr",
    "Domain": "domain-name",
    "Hash": "file",
    "Vulnerability": "vulnerability",
    "TTP": "attack-pattern",
}


def _to_stix_object(entity: dict) -> dict | None:
    """Convert an entity to a STIX 2.1 object."""
    entity_type = entity.get("entity_type", "")
    stix_type = ENTITY_TO_STIX.get(entity_type)
    if not stix_type:
        return None

    stix_id = f"{stix_type}--{entity.get('id', str(uuid_mod.uuid4()))}"
    obj = {
        "type": stix_type,
        "spec_version": "2.1",
        "id": stix_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "modified": datetime.now(timezone.utc).isoformat(),
    }

    name = entity.get("name", "")

    if stix_type == "identity":
        obj["name"] = name
        obj["identity_class"] = "individual" if entity_type == "Person" else "organization"
    elif stix_type == "location":
        obj["name"] = name
    elif stix_type == "threat-actor":
        obj["name"] = name
        obj["threat_actor_types"] = ["unknown"]
    elif stix_type == "malware":
        obj["name"] = name
        obj["is_family"] = True
    elif stix_type == "campaign":
        obj["name"] = name
    elif stix_type == "ipv4-addr":
        obj["value"] = name
    elif stix_type == "domain-name":
        obj["value"] = name
    elif stix_type == "file":
        obj["hashes"] = {"SHA-256": name} if len(name) == 64 else {"SHA-1": name} if len(name) == 40 else {"MD5": name}
    elif stix_type == "vulnerability":
        obj["name"] = name
    elif stix_type == "attack-pattern":
        obj["name"] = name

    return obj


@router.get("/export/graph")
def export_graph_json(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Export the full graph as JSON (nodes + edges)."""
    data = store.get_full_graph(project_id=project_id, limit=10000)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename=graph-export-{project_id[:8]}.json"},
    )


@router.get("/export/entities")
def export_entities_csv(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Export all entities as CSV."""
    entities = store.search_entities(project_id=project_id, limit=10000)

    # Build CSV
    lines = ["id,name,entity_type"]
    for e in entities:
        name = e.get("name", "").replace(",", ";").replace('"', "'")
        lines.append(f'{e.get("id","")},"{name}",{e.get("entity_type","")}')

    csv_content = "\n".join(lines)
    return JSONResponse(
        content={"csv": csv_content, "count": len(entities)},
        headers={"Content-Disposition": f"attachment; filename=entities-{project_id[:8]}.csv"},
    )


@router.get("/export/report/{report_id}")
def export_report(report_id: str, store: GraphStore = Depends(get_graph_store)):
    """Export a specific report."""
    report = store.get_entity(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "title": report.get("name", ""),
        "content": report.get("content", ""),
        "report_type": report.get("report_type", ""),
    }


@router.get("/export/stix")
def export_stix(project_id: str, store: GraphStore = Depends(get_graph_store)):
    """Export the knowledge graph as a STIX 2.1 bundle."""
    entities = store.search_entities(project_id=project_id, limit=10000)
    graph_data = store.get_full_graph(project_id=project_id, limit=10000)

    stix_objects = []
    id_map = {}  # entity_id -> stix_id

    # Convert entities
    for entity in entities:
        stix_obj = _to_stix_object(entity)
        if stix_obj:
            stix_objects.append(stix_obj)
            id_map[entity.get("id", "")] = stix_obj["id"]

    # Convert relationships
    STIX_REL_MAP = {
        "TARGETS": "targets",
        "USES": "uses",
        "ATTRIBUTED_TO": "attributed-to",
        "LOCATED_AT": "located-at",
        "COMMUNICATES_WITH": "communicates-with",
        "ASSOCIATED_WITH": "related-to",
        "BELONGS_TO": "related-to",
        "EXPLOITS": "exploits",
        "RESOLVES_TO": "resolves-to",
    }

    for edge in graph_data.get("edges", []):
        source_stix = id_map.get(edge.get("source_id", ""))
        target_stix = id_map.get(edge.get("target_id", ""))
        if source_stix and target_stix:
            rel_type = STIX_REL_MAP.get(edge.get("rel_type", ""), "related-to")
            stix_objects.append({
                "type": "relationship",
                "spec_version": "2.1",
                "id": f"relationship--{str(uuid_mod.uuid4())}",
                "relationship_type": rel_type,
                "source_ref": source_stix,
                "target_ref": target_stix,
                "created": datetime.now(timezone.utc).isoformat(),
                "modified": datetime.now(timezone.utc).isoformat(),
            })

    bundle = {
        "type": "bundle",
        "id": f"bundle--{str(uuid_mod.uuid4())}",
        "objects": stix_objects,
    }

    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f"attachment; filename=stix-export-{project_id[:8]}.json"},
    )
