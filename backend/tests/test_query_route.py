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
