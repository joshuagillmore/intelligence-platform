"""Route tests for the structured analytic techniques (/api/analysis/*).

Follows the seam used by test_llm_route.py: the single provider selector
(`intel_platform.api.routes.llm._get_provider`) is patched, so nothing here
touches a network LLM. `use_vector` is switched off for ACH so the embedding
provider is never reached either.
"""
import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.routes import llm as llm_routes
from intel_platform.config import settings
from intel_platform.llm.base import LLMProvider, LLMResponse
from intel_platform.models.entities import Document, Organization, Person
from intel_platform.models.relationships import Relationship

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

PROJECT = "test-analysis-project"


class FakeLLMProvider(LLMProvider):
    """Deterministic provider double — records the prompt it was handed."""

    def __init__(self, response_text: str = "Mock analysis"):
        self._response_text = response_text
        self.last_messages: list[dict] | None = None
        self.last_system: str | None = None

    async def generate(self, messages, system="", temperature=0.3, max_tokens=4096):
        self.last_messages = messages
        self.last_system = system
        return LLMResponse(content=self._response_text, model="fake-model", input_tokens=7, output_tokens=3)

    async def stream(self, messages, system="", temperature=0.3, max_tokens=4096):
        yield self._response_text

    def name(self):
        return "fake"


def _patch_provider(monkeypatch, provider):
    async def _fake_get_provider():
        return provider

    monkeypatch.setattr(llm_routes, "_get_provider", _fake_get_provider)


@pytest.fixture
def no_provider(monkeypatch):
    """Simulate a deployment with no LLM configured."""
    _patch_provider(monkeypatch, None)


@pytest.fixture
def seeded_project(graph_store):
    """A small but realistic project: one document, a mentioned person, an orphan org."""
    doc = Document(
        name="Ledger Extract 2026-04",
        project_id=PROJECT,
        url="https://example.invalid/ledger",
        content=(
            "The consignment was routed through Kolvane Holdings on 4 April. "
            "Marek Ilyas signed for it at the depot."
        ),
    )
    person = Person(name="Marek Ilyas", project_id=PROJECT, source_doc_id=doc.id)
    orphan = Organization(name="Unlinked Trading Co", project_id=PROJECT)
    graph_store.create_entity(doc)
    graph_store.create_entity(person)
    graph_store.create_entity(orphan)
    graph_store.create_relationship(
        Relationship(
            source_id=doc.id, target_id=person.id, rel_type="MENTIONS",
            confidence=1.0, source="test", method="test",
        )
    )
    return {"doc": doc, "person": person, "orphan": orphan}


# ── gap analysis ───────────────────────────────────────────────────────────

def test_gaps_degrade_cleanly_without_provider(seeded_project, no_provider):
    resp = client.post(
        "/api/analysis/gaps", json={"project_id": PROJECT}, headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "none"
    assert data["skill_applied"] == "gap_analysis"
    # Deterministic gaps still land, and the body says why there is no narrative.
    assert "No LLM provider is configured" in data["analysis"]
    kinds = {gap["kind"] for gap in data["structural_gaps"]}
    assert "connection" in kinds  # the orphan organization
    assert "provenance" in kinds  # the unrated document
    assert data["coverage"]["documents"] >= 1
    assert data["coverage"]["isolated"] >= 1


def test_gaps_are_grounded_in_measured_coverage(seeded_project, monkeypatch):
    provider = FakeLLMProvider("## Gaps\n\n- Kolvane Holdings is never linked to a source.")
    _patch_provider(monkeypatch, provider)

    resp = client.post(
        "/api/analysis/gaps",
        json={"project_id": PROJECT, "entity_ids": [seeded_project["person"].id]},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis"].startswith("## Gaps")
    assert data["model"] == "fake-model"
    assert data["retrieval_mode"] == "grounded"
    assert data["focus_entities"] == ["Marek Ilyas"]
    # The prompt carried real measured coverage and the retrieved subgraph,
    # not just the entity name.
    prompt = provider.last_messages[0]["content"]
    assert "Measured Coverage (computed from the knowledge graph)" in prompt
    assert "Intelligence Context from Knowledge Graph" in prompt
    assert "Marek Ilyas" in prompt
    # The gap_analysis skill's system prompt was applied.
    assert "intelligence gaps" in (provider.last_system or "").lower()


def test_gaps_on_empty_project(no_provider):
    resp = client.post(
        "/api/analysis/gaps", json={"project_id": "test-analysis-empty"}, headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["coverage"]["entities"] == 0
    assert any(gap["kind"] == "collection" for gap in data["structural_gaps"])


# ── source evaluation ──────────────────────────────────────────────────────

def test_source_evaluation_grades_and_persists_rating(seeded_project, graph_store, monkeypatch):
    doc_id = seeded_project["doc"].id
    provider = FakeLLMProvider(
        "Single-source reporting with limited corroboration.\n\n"
        f"RATINGS:\n{doc_id}: B2\n"
    )
    _patch_provider(monkeypatch, provider)

    resp = client.post(
        "/api/analysis/source-evaluation",
        json={"project_id": PROJECT, "apply_ratings": True},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["documents_evaluated"] == 1
    evaluation = data["evaluations"][0]
    assert evaluation["document_id"] == doc_id
    assert evaluation["admiralty_rating"] == "B2"
    assert data["ratings_applied"] == 1
    # The rating was written back onto the Document node, where Graph-RAG reads it.
    assert graph_store.get_entity(doc_id)["reliability_rating"] == "B2"

    # Grounded in measured provenance, not just the document title.
    prompt = provider.last_messages[0]["content"]
    assert "Entities extracted: 1" in prompt
    assert "Corroboration:" in prompt
    assert "Marek Ilyas" in prompt


def test_source_evaluation_does_not_persist_by_default(seeded_project, graph_store, monkeypatch):
    doc_id = seeded_project["doc"].id
    _patch_provider(monkeypatch, FakeLLMProvider(f"RATINGS:\n{doc_id}: A1\n"))

    resp = client.post(
        "/api/analysis/source-evaluation",
        json={"project_id": PROJECT, "document_ids": [doc_id]},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluations"][0]["admiralty_rating"] == "A1"
    assert data["ratings_applied"] == 0
    assert graph_store.get_entity(doc_id)["reliability_rating"] == ""


def test_source_evaluation_without_provider_returns_measured_signals(seeded_project, no_provider):
    resp = client.post(
        "/api/analysis/source-evaluation", json={"project_id": PROJECT}, headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "none"
    assert "Source Evaluation" in data["analysis"]
    assert "Ledger Extract 2026-04" in data["analysis"]
    assert data["evaluations"][0]["admiralty_rating"] == ""


def test_source_evaluation_with_no_documents(no_provider):
    resp = client.post(
        "/api/analysis/source-evaluation",
        json={"project_id": "test-analysis-empty"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["documents_evaluated"] == 0
    assert "No documents are held" in data["analysis"]


# ── competing hypotheses (ACH) ─────────────────────────────────────────────

def test_hypotheses_parse_and_save_assessment(seeded_project, graph_store, monkeypatch):
    provider = FakeLLMProvider(
        "| Evidence | H1 | H2 |\n|---|---|---|\n| Depot signature | C | I |\n\n"
        "HYPOTHESES:\n"
        "H1 | Ilyas acted as the depot's authorised agent | 0.7\n"
        "H2 | Ilyas signed under another party's instruction | 0.25\n"
    )
    _patch_provider(monkeypatch, provider)

    resp = client.post(
        "/api/analysis/hypotheses",
        json={
            "project_id": PROJECT,
            "question": "Who authorised the consignment?",
            "entity_ids": [seeded_project["person"].id],
            "use_vector": False,
            "save_assessment": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_mode"] == "grounded"
    assert [h["id"] for h in data["hypotheses"]] == ["H1", "H2"]
    assert data["hypotheses"][0]["probability"] == 0.7
    assert data["hypotheses"][0]["probability_label"] == "Likely"
    # The leading hypothesis was persisted as an Assessment linked to the entity.
    assert data["assessment_id"]
    assessment = graph_store.get_entity(data["assessment_id"])
    assert assessment["probability"] == 0.7
    assert "ACH" in assessment["methodology"]

    prompt = provider.last_messages[0]["content"]
    assert "Who authorised the consignment?" in prompt
    assert "Intelligence Context from Knowledge Graph" in prompt
    assert "consistency matrix" in prompt.lower()


def test_hypotheses_do_not_save_when_not_requested(seeded_project, monkeypatch):
    _patch_provider(monkeypatch, FakeLLMProvider("HYPOTHESES:\nH1 | Something happened | 0.5\n"))

    resp = client.post(
        "/api/analysis/hypotheses",
        json={
            "project_id": PROJECT,
            "question": "What happened?",
            "entity_ids": [seeded_project["person"].id],
            "use_vector": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "assessment_id" not in data
    assert data["hypotheses"][0]["probability_label"] == "Roughly Even Chance"


def test_hypotheses_degrade_cleanly_without_provider(seeded_project, no_provider):
    resp = client.post(
        "/api/analysis/hypotheses",
        json={
            "project_id": PROJECT,
            "question": "Who authorised the consignment?",
            "entity_ids": [seeded_project["person"].id],
            "use_vector": False,
            "save_assessment": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "none"
    assert data["hypotheses"] == []
    assert "assessment_id" not in data  # never persist a non-answer
    assert "No LLM provider is configured" in data["analysis"]
    # The retrieved evidence is still handed back for manual work.
    assert "Intelligence Context from Knowledge Graph" in data["analysis"]


def test_analysis_endpoints_require_auth():
    for path in ("/api/analysis/gaps", "/api/analysis/source-evaluation", "/api/analysis/hypotheses"):
        resp = client.post(path, json={"project_id": PROJECT, "question": "x"})
        assert resp.status_code in (401, 403)
