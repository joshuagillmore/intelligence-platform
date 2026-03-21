from intel_platform.services.assessment import AssessmentService
from intel_platform.models.entities import ThreatActor


def test_create_assessment(graph_store):
    actor = ThreatActor(name="APT-TEST", project_id="test-proj-assess")
    graph_store.create_entity(actor)
    svc = AssessmentService(graph_store)
    result = svc.create_assessment(
        entity_id=actor.id,
        project_id="test-proj-assess",
        judgment="Likely state-sponsored",
        probability=0.75,
        analyst="test-analyst",
        methodology="ACH",
    )
    assert result["probability_label"] == "Likely"
    assert result["entity_name"] == "APT-TEST"


def test_create_assessment_entity_not_found(graph_store):
    svc = AssessmentService(graph_store)
    result = svc.create_assessment(
        entity_id="nonexistent",
        project_id="test-proj-assess",
        judgment="Test",
        probability=0.5,
    )
    assert "error" in result
