"""Tests for the Overpass nearby-features lookup (G5). All HTTP mocked."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from intel_platform.services.geo.overpass import (
    _build_query,
    _categorize,
    nearby_features,
)


def _resp(payload):
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def test_categorize():
    assert _categorize({"aeroway": "aerodrome"}) == "airfield"
    assert _categorize({"military": "barracks"}) == "military"
    assert _categorize({"landuse": "military"}) == "military"
    assert _categorize({"power": "plant"}) == "power"
    assert _categorize({"man_made": "tower"}) == "infrastructure"
    assert _categorize({"amenity": "hospital"}) == "emergency"
    assert _categorize({"place": "suburb"}) == "neighbourhood"
    assert _categorize({"shop": "bakery"}) == "feature"


def test_build_query_contains_point_and_selectors():
    q = _build_query(34.0, 44.0, 2000)
    assert "around:2000,34.0,44.0" in q
    assert "aeroway=aerodrome" in q and "[military]" in q


async def test_nearby_features_parses_and_categorizes():
    payload = {"elements": [
        {"type": "way", "center": {"lat": 34.01, "lon": 44.02},
         "tags": {"aeroway": "aerodrome", "name": "Mosul Intl"}},
        {"type": "node", "lat": 34.03, "lon": 44.05,
         "tags": {"military": "barracks", "name": "Base X"}},
        {"type": "node", "lat": 34.0, "lon": 44.0,
         "tags": {"place": "suburb", "name": "Old Quarter"}},
    ]}
    client = MagicMock(post=AsyncMock(return_value=_resp(payload)))
    feats = await nearby_features(client, "http://overpass", 34.0, 44.0)
    cats = {f["name"]: f["category"] for f in feats}
    assert cats["Mosul Intl"] == "airfield"
    assert cats["Base X"] == "military"
    assert cats["Old Quarter"] == "neighbourhood"
    assert all("lat" in f and "lon" in f for f in feats)


async def test_nearby_features_tolerates_bad_response():
    client = MagicMock(post=AsyncMock(return_value=_resp(None)))
    assert await nearby_features(client, "http://overpass", 34.0, 44.0) == []


async def test_nearby_features_handles_post_error():
    client = MagicMock(post=AsyncMock(side_effect=RuntimeError("rate limited")))
    assert await nearby_features(client, "http://overpass", 34.0, 44.0) == []


# --- route ------------------------------------------------------------------

@pytest.fixture
def client():
    from intel_platform.api.app import app
    return TestClient(app)


@pytest.fixture
def auth_header():
    from intel_platform.api.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


def test_nearby_route_404_when_missing(client, auth_header):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store
    store = MagicMock(get_entity=MagicMock(return_value=None))
    app.dependency_overrides[get_graph_store] = lambda: store
    try:
        resp = client.get("/api/geo/nearby/nope", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 404


def test_nearby_route_empty_when_no_coordinates(client, auth_header):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store
    store = MagicMock(get_entity=MagicMock(
        return_value={"id": "e1", "name": "Zzzq-Nowhere", "entity_type": "Location"}))
    app.dependency_overrides[get_graph_store] = lambda: store
    try:
        resp = client.get("/api/geo/nearby/e1", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200 and resp.json()["features"] == []


def test_nearby_route_returns_features(client, auth_header):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store
    store = MagicMock(get_entity=MagicMock(return_value={
        "id": "e1", "name": "X", "entity_type": "Location",
        "latitude": 34.0, "longitude": 44.0,
    }))
    app.dependency_overrides[get_graph_store] = lambda: store
    fake = AsyncMock(return_value=[
        {"name": "Base", "category": "military", "lat": 34.01, "lon": 44.01, "tags": {}},
    ])
    try:
        with patch("intel_platform.services.geo.overpass.nearby_features", new=fake):
            resp = client.get("/api/geo/nearby/e1", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1 and data["features"][0]["category"] == "military"
