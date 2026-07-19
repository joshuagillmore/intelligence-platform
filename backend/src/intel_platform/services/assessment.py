from __future__ import annotations

from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Assessment


class AssessmentService:
    def __init__(self, store: GraphStore):
        self._store = store

    def create_assessment(
        self,
        entity_id: str,
        project_id: str,
        judgment: str,
        probability: float,
        analyst: str = "system",
        methodology: str = "",
    ) -> dict:
        entity = self._store.get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}

        assessment = Assessment(
            name=f"Assessment: {entity.get('name', 'Unknown')}",
            judgment=judgment,
            probability=probability,
            analyst=analyst,
            methodology=methodology,
            project_id=project_id,
        )
        self._store.create_entity(assessment)

        # Link assessment to entity
        from intel_platform.models.relationships import Relationship

        rel = Relationship(
            source_id=assessment.id,
            target_id=entity_id,
            rel_type="ASSESSES",
            confidence=1.0,
            source="assessment_service",
            method="analyst",
        )
        self._store.create_relationship(rel)
        return {
            "assessment_id": assessment.id,
            "entity_id": entity_id,
            "entity_name": entity.get("name", ""),
            "judgment": judgment,
            "probability": probability,
            "probability_label": assessment.probability_label,
        }

    def get_entity_assessments(self, entity_id: str) -> list[dict]:
        rels = self._store.get_relationships(entity_id)
        assessment_ids = [r["target_id"] for r in rels if r["rel_type"] == "ASSESSES"]
        assessments = []
        for aid in assessment_ids:
            a = self._store.get_entity(aid)
            if a:
                assessments.append(a)
        return assessments
