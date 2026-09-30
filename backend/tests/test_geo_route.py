from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_geo_locations():
    resp = client.get("/api/geo/locations", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    assert "locations" in resp.json()
    assert "total" in resp.json()


def test_edge_count_is_the_number_of_edges_drawn(monkeypatch):
    """P-18 (backend half): the map draws `edges`, and `edge_count` is their
    number. The page summed every location's `connection_count` instead —
    all relationships, place-to-place counted twice. This pins the field the
    page now reads."""
    from intel_platform.api.deps import get_graph_store
    from intel_platform.api.routes import geo as geo_routes

    locations = [
        {"id": "l1", "name": "Riga", "entity_type": "Location", "lat": 56.9, "lon": 24.1},
        {"id": "l2", "name": "Tallinn", "entity_type": "Location", "lat": 59.4, "lon": 24.7},
        {"id": "l3", "name": "Oslo", "entity_type": "Location", "lat": 59.9, "lon": 10.7},
    ]
    monkeypatch.setattr(geo_routes, "geolocate_entities", lambda store, pid: [dict(x) for x in locations])

    class _Store:
        def get_relationships_bulk(self, ids):
            shared = {"target_id": "vessel", "target_name": "MV Eagle S", "rel_type": "LOCATED_AT"}
            other = {"target_id": "l2", "target_name": "Tallinn", "rel_type": "NEAR"}
            return {"l1": [shared, other], "l2": [shared], "l3": []}

    app.dependency_overrides[get_graph_store] = lambda: _Store()
    try:
        body = client.get("/api/geo/locations", params={"project_id": "p"}, headers=headers).json()
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert body["edge_count"] == len(body["edges"]) == 1
    assert sum(loc["connection_count"] for loc in body["locations"]) == 3, \
        "connection_count is per-location relationships — not an edge count"
