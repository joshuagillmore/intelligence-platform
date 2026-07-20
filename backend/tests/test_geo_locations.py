"""Tests for the geo-locations aggregation (G1: connect IP/WHOIS geo to the map)."""
import json
from unittest.mock import MagicMock

import intel_platform.services.geocoding as geocoding
from intel_platform.services.geocoding import _extract_coords, geolocate_entities


def test_extract_coords_persisted():
    lat, lng, src = _extract_coords({"latitude": 10.0, "longitude": 20.0})
    assert (lat, lng, src) == (10.0, 20.0, "persisted")


def test_extract_coords_from_geoip_blob():
    blob = json.dumps({"city": "Amsterdam", "lat": 52.37, "lon": 4.9})
    lat, lng, src = _extract_coords({"entity_type": "IPAddress", "geolocation": blob})
    assert src == "geoip"
    assert round(lat, 2) == 52.37 and round(lng, 2) == 4.9


def test_extract_coords_from_gazetteer(monkeypatch):
    monkeypatch.setattr(
        geocoding, "geocode_location",
        lambda name: (55.75, 37.62) if name == "Moscow" else None,
    )
    lat, lng, src = _extract_coords({"name": "Moscow"})
    assert src == "gazetteer" and lat == 55.75


def test_extract_coords_unplaceable(monkeypatch):
    monkeypatch.setattr(geocoding, "geocode_location", lambda name: None)
    assert _extract_coords({"name": "Nowhere-XYZ"}) == (None, None, "")


def test_extract_coords_rejects_out_of_range():
    # A garbage blob (lat 999) must not render off-map — falls through to unplaceable.
    blob = json.dumps({"lat": 999, "lon": 4.9})
    assert _extract_coords({"entity_type": "IPAddress", "geolocation": blob}) == (None, None, "")


def test_extract_coords_keeps_null_island():
    # A real 0.0 (equator/prime meridian) is valid, not "missing".
    lat, lng, src = _extract_coords({"latitude": 0.0, "longitude": 0.0})
    assert (lat, lng) == (0.0, 0.0) and src == "persisted"


def test_geolocate_entities_resolves_ip_and_places_without_writing(monkeypatch):
    monkeypatch.setattr(
        geocoding, "geocode_location",
        lambda name: (55.75, 37.62) if name == "Moscow" else None,
    )
    ip_blob = json.dumps({"city": "Amsterdam", "lat": 52.37, "lon": 4.9})
    nodes = [
        {"id": "ip1", "name": "8.8.8.8", "entity_type": "IPAddress", "geolocation": ip_blob},
        {"id": "loc1", "name": "Moscow", "entity_type": "Location"},
        {"id": "loc2", "name": "Nowhere-XYZ", "entity_type": "Location"},
    ]
    store = MagicMock()
    store.get_geolocatable_entities = MagicMock(return_value=nodes)
    store.update_entity = MagicMock()

    out = {r["id"]: r for r in geolocate_entities(store, "proj")}

    # IP geo now surfaces on the map (was invisible before G1)
    assert out["ip1"]["geocoded"] is True and out["ip1"]["geo_source"] == "geoip"
    assert out["loc1"]["geocoded"] is True and out["loc1"]["geo_source"] == "gazetteer"
    assert out["loc2"]["geocoded"] is False
    # Provenance/confidence (G6): IP geo is approximate, the gazetteer is coarse.
    assert out["ip1"]["geo_confidence"] == "approximate"
    assert out["loc1"]["geo_confidence"] == "coarse"
    # Pure read — no write-back (persisting gazetteer coords would shadow G2's geocoder)
    store.update_entity.assert_not_called()


def test_geo_within_filters_by_bbox(monkeypatch):
    from fastapi.testclient import TestClient

    from intel_platform.api.app import app
    from intel_platform.api.auth import create_access_token
    from intel_platform.api.deps import get_graph_store

    monkeypatch.setattr(geocoding, "geocode_location", lambda name: None)
    nodes = [
        {"id": "a", "name": "Inside", "entity_type": "Location", "latitude": 10.0, "longitude": 10.0},
        {"id": "b", "name": "Outside", "entity_type": "Location", "latitude": 50.0, "longitude": 50.0},
    ]
    store = MagicMock()
    store.get_geolocatable_entities = MagicMock(return_value=nodes)
    app.dependency_overrides[get_graph_store] = lambda: store
    client = TestClient(app)
    header = {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}
    try:
        resp = client.get(
            "/api/geo/within",
            params={"project_id": "p", "min_lat": 0, "min_lng": 0, "max_lat": 20, "max_lng": 20},
            headers=header,
        )
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1 and data["entities"][0]["id"] == "a"
