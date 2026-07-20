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


def test_geolocate_entities_includes_ip_and_persists(monkeypatch):
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
    # Newly-resolved coords are persisted once (ip1 + loc1, not the unplaceable loc2)
    assert store.update_entity.call_count == 2
