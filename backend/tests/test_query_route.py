from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_graph_rag_query():
    response = client.post(
        "/api/query",
        json={"project_id": "nonexistent", "query": "test query"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "context" in data
    assert "query" in data


# ---------------------------------------------------------------------------
# Traversal depth is bounded (A-8)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.fixture
def graph_only_pipeline(monkeypatch):
    """Record the hops the graph-only pipeline is asked for, without Neo4j."""
    from intel_platform.services import graph_rag

    seen: list[int] = []

    async def fake_query(self, query, project_id, max_hops=2, token_budget=8000):
        seen.append(max_hops)
        return {"query": query, "answer": "", "model": "none", "context": ""}

    monkeypatch.setattr(graph_rag.GraphRAGPipeline, "query", fake_query)
    return seen


@pytest.mark.parametrize("hops", [-1, 0, 5, 50])
def test_out_of_range_hops_are_rejected(hops, graph_only_pipeline):
    """A negative depth was interpolated into Cypher (syntax error -> 500); a
    deep one enumerated every path through the ATT&CK hubs with no LIMIT."""
    resp = client.post(
        "/api/query",
        json={"project_id": "test-a8", "query": "q", "max_hops": hops, "use_vector": False},
        headers=headers,
    )
    assert resp.status_code == 422
    assert graph_only_pipeline == []


@pytest.mark.parametrize("hops", [1, 4])
def test_hops_at_the_bounds_are_accepted(hops, graph_only_pipeline):
    resp = client.post(
        "/api/query",
        json={"project_id": "test-a8", "query": "q", "max_hops": hops, "use_vector": False},
        headers=headers,
    )
    assert resp.status_code == 200
    assert graph_only_pipeline == [hops]


@pytest.mark.parametrize("hops", [0, 5])
def test_subgraph_hops_are_bounded(hops):
    resp = client.get("/api/subgraph/any-id", params={"hops": hops}, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Contract 6: when no model ran, the answer is empty and the reason is given
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from intel_platform.db.engine import get_db  # noqa: E402

CONTEXT = "## Entities\n- APT Example (ThreatActor)\n- Kolvane (Organization)"


class _Provider:
    def __init__(self, content=None, error=None):
        self.content, self.error = content, error

    async def generate(self, **kwargs):
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.content, model="test-model", total_tokens=42)


@pytest.fixture
def hybrid(monkeypatch):
    """Hybrid retrieval returning a fixed context, with the provider swappable."""
    from intel_platform.api.routes import llm as llm_route
    from intel_platform.services import hybrid_retrieval

    async def retrieve(self, query, project_id, max_hops=2, token_budget=8000):
        return {"context": CONTEXT, "node_count": 2, "edge_count": 1, "vector_results": []}

    async def no_db():
        yield None

    monkeypatch.setattr(hybrid_retrieval.HybridRetriever, "retrieve", retrieve)
    app.dependency_overrides[get_db] = no_db

    def use(provider):
        async def get_provider():
            return provider
        monkeypatch.setattr(llm_route, "_get_provider", get_provider)

    yield use
    app.dependency_overrides.pop(get_db, None)


def _ask(use_vector=True):
    resp = client.post(
        "/api/query", json={"project_id": "test-c6", "query": "Who targeted Kolvane?", "use_vector": use_vector},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


class TestDegradedAnswer:
    def test_a_provider_failure_returns_no_answer_and_a_sanitised_reason(self, hybrid):
        hybrid(_Provider(error=RuntimeError("connect to http://10.0.0.5:11434 refused: model qwen missing")))
        data = _ask()
        assert data["answer"] == ""
        assert data["model"] == "none"
        assert data["llm_error"]
        assert "10.0.0.5" not in data["llm_error"] and "qwen" not in data["llm_error"]
        assert data["context"] == CONTEXT

    def test_no_provider_is_a_degraded_answer_not_the_context(self, hybrid):
        hybrid(None)
        data = _ask()
        assert data["answer"] == ""
        assert data["model"] == "none"
        assert "configured" in data["llm_error"]

    @pytest.mark.parametrize("content", ["", "   \n"])
    def test_an_empty_reply_is_a_degraded_answer(self, hybrid, content):
        hybrid(_Provider(content=content))
        data = _ask()
        assert data["answer"] == ""
        assert data["model"] == "none"
        assert data["llm_error"]

    def test_a_real_answer_carries_no_error(self, hybrid):
        hybrid(_Provider(content="APT Example targeted Kolvane."))
        data = _ask()
        assert data["answer"] == "APT Example targeted Kolvane."
        assert data["model"] == "test-model"
        assert data["llm_error"] is None


class TestDegradedAnswerGraphOnly:
    @pytest.fixture
    def pipeline(self, monkeypatch):
        from intel_platform.services import graph_rag

        def use(result):
            async def query(self, query, project_id, max_hops=2, token_budget=8000):
                return dict(result)
            monkeypatch.setattr(graph_rag.GraphRAGPipeline, "query", query)
        return use

    @pytest.mark.parametrize("fallback", [CONTEXT, "LLM generation failed. Using raw graph context as fallback."])
    def test_the_pipelines_fallback_text_is_not_an_answer(self, pipeline, fallback):
        pipeline({"query": "q", "answer": fallback, "model": "none", "tokens_used": 0, "context": CONTEXT})
        data = _ask(use_vector=False)
        assert data["answer"] == ""
        assert data["model"] == "none"
        assert data["llm_error"]
        assert data["context"] == CONTEXT

    def test_a_model_that_returned_nothing_is_degraded(self, pipeline):
        """The pipeline substitutes the context for an empty reply."""
        pipeline({"query": "q", "answer": CONTEXT, "model": "test-model", "tokens_used": 3, "context": CONTEXT})
        data = _ask(use_vector=False)
        assert data["answer"] == ""
        assert data["llm_error"]

    def test_a_real_answer_passes_through(self, pipeline):
        pipeline({"query": "q", "answer": "An answer.", "model": "test-model", "tokens_used": 3, "context": CONTEXT})
        data = _ask(use_vector=False)
        assert data["answer"] == "An answer."
        assert data["model"] == "test-model"
        assert data["llm_error"] is None
