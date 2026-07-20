"""Tests for the Nominatim geocode provider (G2). All HTTP mocked."""
from unittest.mock import AsyncMock, MagicMock

from intel_platform.enrichment.providers.geocode import GeocodeProvider


def _resp(payload):
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _client(get_impl):
    client = MagicMock()
    client.get = AsyncMock(side_effect=get_impl)
    return client


async def test_geocode_maps_admin_hierarchy_and_parents():
    async def get(url, params=None, headers=None, timeout=15):
        return _resp([{
            "lat": "43.73", "lon": "44.66",
            "display_name": "Mozdok, North Ossetia-Alania, Russia",
            "addresstype": "town", "type": "town",
            "address": {
                "town": "Mozdok", "county": "Mozdoksky District",
                "state": "North Ossetia-Alania", "country": "Russia",
                "country_code": "ru", "postcode": "363750", "neighbourhood": "Center",
            },
        }])

    result = await GeocodeProvider(client=_client(get)).lookup("Mozdok", "Location")
    p = result.properties
    assert round(p["latitude"], 2) == 43.73 and round(p["longitude"], 2) == 44.66
    assert p["geo_source"] == "nominatim"
    assert p["country"] == "Russia" and p["country_code"] == "RU"
    assert p["admin1"] == "North Ossetia-Alania"       # state/province
    assert p["admin2"] == "Mozdoksky District"          # county/district
    assert p["city"] == "Mozdok" and p["postal_code"] == "363750"
    assert p["neighbourhood"] == "Center"
    parents = {(r.name, r.rel_type) for r in result.related}
    assert ("Russia", "BELONGS_TO") in parents
    assert ("North Ossetia-Alania", "BELONGS_TO") in parents


async def test_geocode_does_not_self_link_a_country():
    async def get(url, params=None, headers=None, timeout=15):
        return _resp([{
            "lat": "60.0", "lon": "90.0", "display_name": "Russia", "addresstype": "country",
            "address": {"country": "Russia", "country_code": "ru"},
        }])

    result = await GeocodeProvider(client=_client(get)).lookup("Russia", "Country")
    # geocoding "Russia" must not create a "Russia" BELONGS_TO parent (self-link)
    assert all(r.name.lower() != "russia" for r in result.related)


async def test_geocode_no_result_is_empty():
    async def get(url, params=None, headers=None, timeout=15):
        return _resp([])

    result = await GeocodeProvider(client=_client(get)).lookup("Nowhere-XYZ", "Location")
    assert result.properties == {}


async def test_geocode_tolerates_malformed_json():
    async def get(url, params=None, headers=None, timeout=15):
        return _resp(None)

    result = await GeocodeProvider(client=_client(get)).lookup("x", "Location")
    assert result.properties == {}
