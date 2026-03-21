from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from intel_platform.api.deps import get_graph_store, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.reports import ReportService

router = APIRouter(dependencies=[Depends(verify_api_key)])


class SaveReportRequest(BaseModel):
    project_id: str
    title: str
    content: str
    report_type: str = "general"
    entity_ids: list[str] = []
    analyst: str = "system"


@router.post("/reports")
def save_report(req: SaveReportRequest, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    return svc.save_report(
        project_id=req.project_id, title=req.title, content=req.content,
        report_type=req.report_type, entity_ids=req.entity_ids, analyst=req.analyst,
    )


@router.get("/reports")
def list_reports(project_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    return svc.list_reports(project_id)


@router.get("/reports/{report_id}")
def get_report(report_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    report = svc.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, store: GraphStore = Depends(get_graph_store)):
    svc = ReportService(store)
    svc.delete_report(report_id)
    return {"status": "deleted"}
