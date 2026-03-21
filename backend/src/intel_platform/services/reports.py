from __future__ import annotations
import uuid
from datetime import datetime, timezone
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Report
from intel_platform.models.relationships import Relationship


class ReportService:
    def __init__(self, store: GraphStore):
        self._store = store

    def save_report(
        self, project_id: str, title: str, content: str, report_type: str,
        entity_ids: list[str] | None = None, analyst: str = "system",
    ) -> dict:
        report = Report(
            name=title,
            report_type=report_type,
            content=content,
            project_id=project_id,
        )
        self._store.create_entity(report)

        # Link report to source entities
        if entity_ids:
            for eid in entity_ids:
                try:
                    rel = Relationship(
                        source_id=report.id, target_id=eid,
                        rel_type="MENTIONS", confidence=1.0,
                        source="report_service", method="analyst",
                    )
                    self._store.create_relationship(rel)
                except ValueError:
                    pass  # Skip if MENTIONS not in allowlist

        return {
            "report_id": report.id,
            "title": title,
            "report_type": report_type,
            "content_length": len(content),
            "linked_entities": len(entity_ids or []),
        }

    def list_reports(self, project_id: str) -> list[dict]:
        reports = self._store.search_entities(
            project_id=project_id, entity_type="Report", limit=100,
        )
        return reports

    def get_report(self, report_id: str) -> dict | None:
        return self._store.get_entity(report_id)

    def delete_report(self, report_id: str) -> None:
        self._store.delete_entity(report_id)
