from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore

router = APIRouter(dependencies=[Depends(verify_api_key)])


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
        return {"error": "Report not found"}
    return {
        "title": report.get("name", ""),
        "content": report.get("content", ""),
        "report_type": report.get("report_type", ""),
    }
