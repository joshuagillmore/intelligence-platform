"""Products never ship a failure as content, and never pass a default off as a judgement.

`POST /reports/generate` and `POST /assess/generate` used to answer an LLM
failure with 200 and `content: "Report generation failed…"`. The products page
showed "Report Ready" with a green "Grounded in N entities" badge and let the
analyst save, export and print the error text under a classification marking.
They now raise 503 with a fixed, detail-free message.

`/assess/generate` also stored the 0.5 fallback whenever the reply's
probability was unreadable — "15%" read as 1.0 before that — and nothing in the
response said the stored value was a default. `probability_parsed` says so.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.deps import get_graph_store
from intel_platform.api.routes import assess as assess_routes
from intel_platform.api.routes import llm as llm_routes
from intel_platform.config import settings
from intel_platform.db.engine import get_db
from intel_platform.llm.base import LLMProvider, LLMResponse

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


class _Provider(LLMProvider):
    def __init__(self, text: str = "", fail: bool = False):
        self._text = text
        self._fail = fail

    async def generate(self, messages, system="", temperature=0.3, max_tokens=4096):
        if self._fail:
            raise RuntimeError("upstream exploded: secret-host:11434 said no")
        return LLMResponse(content=self._text, model="fake-model", input_tokens=1, output_tokens=1)

    async def stream(self, messages, system="", temperature=0.3, max_tokens=4096):
        yield self._text

    def name(self):
        return "fake"


class _Store:
    """Enough of GraphStore for AssessmentService and the report route."""

    def __init__(self):
        self.created: list = []
        self.relationships: list = []

    def get_entity(self, entity_id):
        return {"id": entity_id, "name": "APT-Test", "entity_type": "ThreatActor", "project_id": "p1"}

    def create_entity(self, entity):
        self.created.append(entity)
        return {}

    def create_relationship(self, rel):
        self.relationships.append(rel)
        return {}


class _Session:
    async def get(self, *_a, **_k):
        return None


@pytest.fixture
def store(monkeypatch):
    s = _Store()
    app.dependency_overrides[get_graph_store] = lambda: s

    async def _db():
        yield _Session()

    app.dependency_overrides[get_db] = _db

    async def _no_rag(self, query, project_id, *a, **k):
        return {"context": ""}

    from intel_platform.services import graph_rag
    monkeypatch.setattr(graph_rag.GraphRAGPipeline, "query", _no_rag)
    yield s
    app.dependency_overrides.pop(get_graph_store, None)
    app.dependency_overrides.pop(get_db, None)


def _use(monkeypatch, provider):
    async def _get():
        return provider
    monkeypatch.setattr(llm_routes, "_get_provider", _get)


class TestAssessGenerate:
    def _post(self):
        return client.post(
            "/api/assess/generate",
            json={"entity_id": "e1", "project_id": "p1", "probability": 0.5},
            headers=headers,
        )

    def test_a_stated_probability_is_stored_and_flagged_parsed(self, store, monkeypatch):
        _use(monkeypatch, _Provider("## Assessment\n...\n**PROBABILITY:** **0.70**\nCONFIDENCE_LABEL: Likely"))
        resp = self._post()
        assert resp.status_code == 200
        body = resp.json()
        assert body["probability"] == 0.70
        assert body["probability_parsed"] is True

    @pytest.mark.parametrize("reply", [
        "PROBABILITY: 15%",                                   # read as 1.0 before the boundary
        "| PROBABILITY | 12.5% |",
        "We judge it likely, perhaps seventy percent.",       # prose, no label
    ])
    def test_an_unreadable_probability_is_the_fallback_and_says_so(self, store, monkeypatch, reply):
        _use(monkeypatch, _Provider(reply))
        body = self._post().json()
        assert body["probability"] == 0.5
        assert body["probability_parsed"] is False

    def test_generation_failure_is_503_not_200(self, store, monkeypatch):
        _use(monkeypatch, _Provider(fail=True))
        resp = self._post()
        assert resp.status_code == 503
        assert resp.json()["detail"] == "LLM provider unavailable"
        assert "secret-host" not in resp.text
        assert store.created == [], "a failed generation must not be saved as an assessment"

    def test_no_provider_is_503(self, store, monkeypatch):
        _use(monkeypatch, None)
        resp = self._post()
        assert resp.status_code == 503
        assert resp.json()["detail"] == "LLM provider unavailable"

    def test_the_link_carries_the_project(self, store, monkeypatch):
        """Contract 16: a Relationship built here names its project."""
        _use(monkeypatch, _Provider("PROBABILITY: 0.6"))
        self._post()
        assert store.relationships
        assert getattr(store.relationships[0], "project_id", "p1") == "p1"

    def test_the_route_has_no_private_probability_parser(self):
        """One parser, in llm_output. The duplicate drifted from it before."""
        assert not hasattr(assess_routes, "extract_probability")
        assert not hasattr(assess_routes, "_PROBABILITY_LINE")


class TestReportsGenerate:
    def _post(self, **extra):
        return client.post(
            "/api/reports/generate",
            json={"project_id": "p1", "skill_name": "report_writing", **extra},
            headers=headers,
        )

    def test_generation_failure_is_503_not_a_report(self, store, monkeypatch):
        _use(monkeypatch, _Provider(fail=True))
        resp = self._post()
        assert resp.status_code == 503
        assert resp.json()["detail"] == "LLM provider unavailable"
        assert "content" not in resp.json()
        assert "secret-host" not in resp.text

    def test_no_provider_is_503(self, store, monkeypatch):
        _use(monkeypatch, None)
        resp = self._post()
        assert resp.status_code == 503
        assert resp.json()["detail"] == "LLM provider unavailable"

    def test_an_empty_reply_is_503_not_an_empty_report(self, store, monkeypatch):
        """A provider answering "" is a failure wearing a success shape."""
        _use(monkeypatch, _Provider("   "))
        assert self._post().status_code == 503

    def test_a_stated_probability_is_reported_with_its_flag(self, store, monkeypatch):
        _use(monkeypatch, _Provider("Body.\n**PROBABILITY:** 0.35"))
        body = self._post().json()
        assert body["probability"] == 0.35
        assert body["probability_parsed"] is True

    def test_a_percentage_is_not_reported_as_a_probability(self, store, monkeypatch):
        _use(monkeypatch, _Provider("Body.\nPROBABILITY: 15%"))
        body = self._post().json()
        assert "probability" not in body
        assert body["probability_parsed"] is False
