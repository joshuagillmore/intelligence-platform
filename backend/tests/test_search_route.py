import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.deps import get_graph_store
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_search():
    resp = client.get("/api/search", params={"project_id": "test", "q": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    assert "documents" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# Contract 11: `total` is the true match count, not the page length
# ---------------------------------------------------------------------------

class _SearchStore:
    def __init__(self, rows, total):
        self.rows, self.total = rows, total
        self.seen: dict = {}

    def search_entities(self, project_id, query="", entity_type=None, limit=50, offset=0):
        self.seen = {"query": query, "limit": limit}
        return self.rows[:limit]

    def count_entities(self, project_id, query="", entity_type=None):
        self.seen["count_query"] = query
        return self.total


ROWS = (
    [{"id": f"e{i}", "name": f"Kolvane {i}", "entity_type": "Organization"} for i in range(3)]
    + [{"id": "d1", "name": "Kolvane report", "entity_type": "Document", "reliability_rating": "B2",
        "content": "x" * 500}]
    + [{"id": "r1", "name": "Kolvane brief", "entity_type": "Report", "report_type": "brief", "content": "y"}]
)


@pytest.fixture
def store():
    holder = {}

    def use(rows, total):
        holder["s"] = _SearchStore(rows, total)
        app.dependency_overrides[get_graph_store] = lambda: holder["s"]
        return holder["s"]

    yield use
    app.dependency_overrides.pop(get_graph_store, None)


def _search(**params):
    return client.get("/api/search", params={"project_id": "test-c11", "q": "kolvane", **params}, headers=headers)


def test_total_is_the_true_count_and_truncation_is_reported(store):
    s = store(ROWS, total=120)
    data = _search(limit=5).json()
    assert data["count"] == 5
    assert data["total"] == 120
    assert data["truncated"] is True
    assert s.seen["count_query"] == "kolvane", "the count must describe the same matches as the page"


def test_a_complete_page_is_not_truncated(store):
    store(ROWS, total=5)
    data = _search().json()
    assert (data["count"], data["total"], data["truncated"]) == (5, 5, False)


def test_results_is_the_flat_page_and_the_categories_are_kept(store):
    store(ROWS, total=5)
    data = _search().json()
    assert [r["id"] for r in data["results"]] == ["e0", "e1", "e2", "d1", "r1"]
    assert [e["id"] for e in data["entities"]] == ["e0", "e1", "e2"]
    assert data["documents"] == [{"id": "d1", "name": "Kolvane report", "entity_type": "Document",
                                  "reliability": "B2", "preview": "x" * 200}]
    assert data["reports"][0]["report_type"] == "brief"
    assert data["results"][3] == data["documents"][0]


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_out_of_range_limits_are_rejected(store, limit):
    store(ROWS, total=5)
    assert _search(limit=limit).status_code == 422
