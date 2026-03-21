from intel_platform.models.entities import (
    Entity,
    Person,
    Organization,
    IPAddress,
    Domain,
    ThreatActor,
    Campaign,
    Document,
    Topic,
    Assessment,
    EntityType,
)
from intel_platform.models.relationships import Relationship, CorroborationAgreement


def test_person_entity():
    p = Person(name="John Doe", aliases=["JD"], roles=["analyst"], project_id="proj-1")
    assert p.entity_type == EntityType.PERSON
    assert p.name == "John Doe"


def test_entity_type_enum():
    assert EntityType.PERSON.value == "Person"
    assert EntityType.THREAT_ACTOR.value == "ThreatActor"
    assert EntityType.IP_ADDRESS.value == "IPAddress"


def test_relationship_defaults():
    r = Relationship(
        source_id="a",
        target_id="b",
        rel_type="ASSOCIATED_WITH",
        confidence=0.8,
        source="doc-1",
        method="llm",
    )
    assert r.corroboration_count == 1
    assert r.corroboration_agreement == CorroborationAgreement.AGREE


def test_corroboration_agreement_enum():
    assert CorroborationAgreement.AGREE.value == "AGREE"
    assert CorroborationAgreement.PARTIAL.value == "PARTIAL"
    assert CorroborationAgreement.CONFLICT.value == "CONFLICT"


def test_assessment_probability_label():
    a = Assessment(
        name="Test assessment",
        judgment="Likely affiliated",
        probability=0.75,
        analyst="analyst-1",
        project_id="proj-1",
    )
    assert a.probability_label == "Likely"


def test_assessment_probability_boundaries():
    a = Assessment(name="t", judgment="t", probability=0.05, analyst="a", project_id="p")
    assert a.probability_label == "Very Unlikely"
    a2 = Assessment(name="t", judgment="t", probability=0.95, analyst="a", project_id="p")
    assert a2.probability_label == "Almost Certain"


def test_document_entity():
    d = Document(
        name="Report.pdf",
        url="https://example.com/report.pdf",
        reliability_rating="B2",
        project_id="proj-1",
    )
    assert d.entity_type == EntityType.DOCUMENT
