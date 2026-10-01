from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings
from tests.ids import tp

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

    def __init__(self, nodes, edges, truncated=None, total=None):
        self.nodes, self.edges, self.truncated = nodes, edges, truncated
        self.total = len(nodes) if total is None else total
        self.calls: list[dict] = []

    def count_entities(self, project_id, query="", entity_type=None):
        return self.total

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
        resp = client.get("/api/graph", params={"project_id": tp("a4"), "limit": 1}, headers=headers)
        assert resp.status_code == 200
        assert tp("a4") not in graph_cache._graphs

    def test_an_existing_analytics_graph_is_not_used_for_the_display(self, fake_store):
        import networkx as nx

        stale = nx.DiGraph()
        stale.add_node("ghost")
        graph_cache.get_or_build_graph(tp("a4"), lambda: stale)
        fake_store(_FakeStore([_node(1), _node(2)], [
            {"source_id": "n1", "target_id": "n2", "rel_type": "USES", "confidence": 0.9},
        ]))
        data = client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()
        degrees = {n["id"]: n["degree"] for n in data["nodes"]}
        assert degrees == {"n1": 1, "n2": 1}

    def test_truncated_is_passed_through(self, fake_store):
        fake_store(_FakeStore([_node(1)], [], truncated=True))
        data = client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()
        assert data["truncated"] is True

    def test_untruncated_is_passed_through(self, fake_store):
        fake_store(_FakeStore([_node(1)], [], truncated=False))
        data = client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()
        assert data["truncated"] is False

    def test_total_nodes_is_the_projects_true_node_count(self, fake_store):
        fake_store(_FakeStore([_node(1), _node(2)], [], total=5486))
        data = client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()
        assert data["total_nodes"] == 5486
        assert data["node_count"] == 2

    def test_truncated_follows_the_true_count_when_the_store_does_not_say(self, fake_store):
        fake_store(_FakeStore([_node(1), _node(2)], [], total=3))
        data = client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()
        assert data["truncated"] is True
        fake_store(_FakeStore([_node(1), _node(2)], [], total=2))
        data = client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()
        assert data["truncated"] is False

    @pytest.mark.parametrize("limit", [0, -1, 10001])
    def test_out_of_range_limits_are_rejected(self, fake_store, limit):
        store = fake_store(_FakeStore([_node(1)], []))
        resp = client.get("/api/graph", params={"project_id": tp("a4"), "limit": limit}, headers=headers)
        assert resp.status_code == 422
        assert store.calls == []


class TestEdgePayload:
    """Contract 4: the network panel said "No captured evidence — re-run
    extraction" for every edge and showed `[object Object]` as its source
    document, because /graph never sent evidence, method or provenance."""

    EDGE = {
        "source_id": "n1", "target_id": "n2", "rel_type": "TARGETS", "confidence": 0.8,
        "evidence": "APT Example targeted Kolvane in March.", "method": "llm",
        "source_doc_id": "doc-123", "polarity": "denies",
        "first_seen": "2026-03-01T00:00:00+00:00", "last_seen": "2026-03-02T00:00:00+00:00",
        "corroboration_sources": ["doc-123", "doc-456"],
    }

    def _edges(self, fake_store, edge):
        fake_store(_FakeStore([_node(1), _node(2)], [edge]))
        return client.get("/api/graph", params={"project_id": tp("a4")}, headers=headers).json()["edges"]

    def test_edges_carry_evidence_method_provenance_and_polarity(self, fake_store):
        (edge,) = self._edges(fake_store, self.EDGE)
        assert edge == {
            "source_id": "n1", "target_id": "n2", "rel_type": "TARGETS", "confidence": 0.8,
            "evidence": "APT Example targeted Kolvane in March.", "method": "llm",
            "source_doc_id": "doc-123", "polarity": "denies",
            "first_seen": "2026-03-01T00:00:00+00:00", "last_seen": "2026-03-02T00:00:00+00:00",
        }

    def test_an_edge_built_before_provenance_existed_gets_strings_not_nulls(self, fake_store):
        (edge,) = self._edges(fake_store, {"source_id": "n1", "target_id": "n2", "rel_type": "USES"})
        assert edge["evidence"] == ""
        assert edge["method"] == ""
        assert edge["source_doc_id"] == ""
        assert edge["polarity"] == "asserts"
        assert edge["confidence"] == 0.5
