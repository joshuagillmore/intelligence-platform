from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_search_entities():
    response = client.get(
        "/api/entities", params={"project_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_entity_not_found():
    response = client.get("/api/entities/nonexistent-id", headers=headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Traversals are scoped to a project (A-7, contract 2)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from intel_platform.api.deps import get_graph_store  # noqa: E402


class _TraversalStore:
    """Records the scope each traversal was asked for (no Neo4j needed)."""

    ENTITIES = {
        "e1": {"id": "e1", "name": "APT Example", "project_id": "proj-a"},
        "e2": {"id": "e2", "name": "Kolvane", "project_id": "proj-a"},
        "t1566": {"id": "t1566", "name": "Phishing", "entity_type": "AttackTechnique"},
    }

    def __init__(self):
        self.subgraph_calls: list[dict] = []
        self.path_calls: list[dict] = []

    def get_entity(self, entity_id):
        return self.ENTITIES.get(entity_id)

    def get_subgraph(self, entity_id, hops=1, project_id=None):
        self.subgraph_calls.append({"entity_id": entity_id, "hops": hops, "project_id": project_id})
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}

    def find_shortest_path(self, entity_id_1, entity_id_2, project_id=None):
        self.path_calls.append({"ids": (entity_id_1, entity_id_2), "project_id": project_id})
        return {"nodes": [], "edges": [], "path_length": -1, "found": False}


@pytest.fixture
def traversal_store():
    store = _TraversalStore()
    app.dependency_overrides[get_graph_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_graph_store, None)


class TestTraversalScope:
    def test_subgraph_is_scoped_to_the_start_entitys_project(self, traversal_store):
        resp = client.get("/api/subgraph/e1", params={"hops": 2}, headers=headers)
        assert resp.status_code == 200
        assert traversal_store.subgraph_calls == [{"entity_id": "e1", "hops": 2, "project_id": "proj-a"}]

    def test_an_explicit_project_scopes_the_subgraph(self, traversal_store):
        client.get("/api/subgraph/e1", params={"project_id": "proj-b"}, headers=headers)
        assert traversal_store.subgraph_calls[0]["project_id"] == "proj-b"

    def test_a_catalog_start_node_needs_a_project(self, traversal_store):
        """ATT&CK nodes are shared by every project; walking out of one unscoped
        reaches other projects' entities and, through GraphRAG, their documents."""
        resp = client.get("/api/subgraph/t1566", headers=headers)
        assert resp.status_code == 400
        assert traversal_store.subgraph_calls == []

    def test_a_catalog_start_node_with_a_project_is_scoped(self, traversal_store):
        client.get("/api/subgraph/t1566", params={"project_id": "proj-a"}, headers=headers)
        assert traversal_store.subgraph_calls[0]["project_id"] == "proj-a"

    def test_an_unknown_start_entity_returns_an_empty_subgraph(self, traversal_store):
        resp = client.get("/api/subgraph/missing", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["nodes"] == []
        assert traversal_store.subgraph_calls == []

    def test_shortest_path_is_scoped_to_the_entities_project(self, traversal_store):
        resp = client.get("/api/paths/e1/e2", headers=headers)
        assert resp.status_code == 200
        assert traversal_store.path_calls == [{"ids": ("e1", "e2"), "project_id": "proj-a"}]

    def test_shortest_path_between_catalog_nodes_needs_a_project(self, traversal_store):
        resp = client.get("/api/paths/t1566/t1566", headers=headers)
        assert resp.status_code == 400
