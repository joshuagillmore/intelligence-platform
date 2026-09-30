from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_get_graph():
    response = client.get(
        "/api/graph", params={"project_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


def test_get_communities():
    response = client.get(
        "/api/communities", params={"project_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /graph is a display view: it must not feed the analytics cache (A-4)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from intel_platform.api.deps import get_graph_store  # noqa: E402
from intel_platform.services.graph_cache import graph_cache  # noqa: E402


class _FakeStore:
    """Stands in for GraphStore on the routes under test (no Neo4j needed)."""

    def __init__(self, nodes, edges, truncated=None):
        self.nodes, self.edges, self.truncated = nodes, edges, truncated
        self.calls: list[dict] = []

    def get_full_graph(self, project_id, limit=500):
        self.calls.append({"project_id": project_id, "limit": limit})
        data = {"nodes": self.nodes[:limit], "edges": self.edges}
        if self.truncated is not None:
            data["truncated"] = self.truncated
        return data

    def get_project(self, project_id):
        return {"id": project_id}

    def search_entities(self, **kwargs):
        return []


def _node(i):
    return {"id": f"n{i}", "name": f"Node {i}", "entity_type": "Person", "entity_category": "Person"}


@pytest.fixture
def fake_store():
    holder: dict = {}

    def install(store):
        holder["store"] = store
        app.dependency_overrides[get_graph_store] = lambda: store
        return store

    graph_cache.clear()
    yield install
    app.dependency_overrides.pop(get_graph_store, None)
    graph_cache.clear()


class TestDisplayGraphDoesNotPoisonAnalytics:
    def test_a_truncated_display_graph_is_not_cached_for_analytics(self, fake_store):
        """`/graph?limit=1` cached a one-node graph under the project key that
        centrality, communities and statistics read for 300 s."""
        fake_store(_FakeStore([_node(1), _node(2), _node(3)], []))
        resp = client.get("/api/graph", params={"project_id": "test-a4", "limit": 1}, headers=headers)
        assert resp.status_code == 200
        assert "test-a4" not in graph_cache._graphs

    def test_an_existing_analytics_graph_is_not_used_for_the_display(self, fake_store):
        import networkx as nx

        stale = nx.DiGraph()
        stale.add_node("ghost")
        graph_cache.get_or_build_graph("test-a4", lambda: stale)
        fake_store(_FakeStore([_node(1), _node(2)], [
            {"source_id": "n1", "target_id": "n2", "rel_type": "USES", "confidence": 0.9},
        ]))
        data = client.get("/api/graph", params={"project_id": "test-a4"}, headers=headers).json()
        degrees = {n["id"]: n["degree"] for n in data["nodes"]}
        assert degrees == {"n1": 1, "n2": 1}

    def test_truncated_is_passed_through(self, fake_store):
        fake_store(_FakeStore([_node(1)], [], truncated=True))
        data = client.get("/api/graph", params={"project_id": "test-a4"}, headers=headers).json()
        assert data["truncated"] is True

    def test_untruncated_is_passed_through(self, fake_store):
        fake_store(_FakeStore([_node(1)], [], truncated=False))
        data = client.get("/api/graph", params={"project_id": "test-a4"}, headers=headers).json()
        assert data["truncated"] is False

    @pytest.mark.parametrize("limit", [0, -1, 10001])
    def test_out_of_range_limits_are_rejected(self, fake_store, limit):
        store = fake_store(_FakeStore([_node(1)], []))
        resp = client.get("/api/graph", params={"project_id": "test-a4", "limit": limit}, headers=headers)
        assert resp.status_code == 422
        assert store.calls == []
