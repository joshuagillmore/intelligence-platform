"""Route tests for the enrichment API (auth + service wiring)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from tests.ids import tp


@pytest.fixture
def client():
    from intel_platform.api.app import app
    return TestClient(app)


@pytest.fixture
def auth_header():
    from intel_platform.api.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


def test_list_providers_reports_free_tier(client, auth_header):
    resp = client.get("/api/enrichment/providers", headers=auth_header)
    assert resp.status_code == 200
    providers = {p["name"]: p for p in resp.json()["providers"]}
    for name in ("dns", "geoip", "kev", "nvd", "rdap", "certs"):
        assert name in providers
    # free tier -> no key required, treated as usable
    assert providers["dns"]["requires_key"] is False
    assert providers["dns"]["has_key"] is True
    assert "IPAddress" in providers["geoip"]["supported_types"]


def test_investigate_requires_auth(client):
    resp = client.post("/api/enrichment/entities/e1")
    assert resp.status_code in (401, 403)


def test_investigate_404_when_entity_missing(client, auth_header):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store

    store = MagicMock()
    store.get_entity = MagicMock(return_value=None)
    app.dependency_overrides[get_graph_store] = lambda: store
    try:
        resp = client.post("/api/enrichment/entities/nope", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 404


def test_investigate_returns_service_result(client, auth_header):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store

    app.dependency_overrides[get_graph_store] = lambda: MagicMock()
    fake = MagicMock()
    fake.enrich_entity = AsyncMock(return_value={
        "entity_id": "e1", "observable": "8.8.8.8",
        "providers": {"geoip": {"status": "ok"}},
    })
    try:
        with patch("intel_platform.api.routes.enrichment._service", return_value=fake):
            resp = client.post("/api/enrichment/entities/e1", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200
    assert resp.json()["providers"]["geoip"]["status"] == "ok"


def test_refresh_400_on_unknown_provider(client, auth_header):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store

    app.dependency_overrides[get_graph_store] = lambda: MagicMock()
    fake = MagicMock()
    # unknown provider -> service returns no providers (entity exists, no error)
    fake.enrich_entity = AsyncMock(return_value={
        "entity_id": "e1", "observable": "8.8.8.8", "providers": {},
    })
    try:
        with patch("intel_platform.api.routes.enrichment._service", return_value=fake):
            resp = client.post(
                "/api/enrichment/entities/e1/refresh?provider=bogus", headers=auth_header
            )
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 400


def test_cached_view_reads_a_vulnerability_under_its_cve_id(client, auth_header):
    # The service caches KEV/NVD under the CVE id (E-3); the read must use the
    # same key or a named vulnerability never shows its enrichment.
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store

    store = MagicMock()
    store.get_entity = MagicMock(return_value={
        "id": "v1", "name": "Log4Shell", "entity_type": "Vulnerability",
        "project_id": tp("p"), "cve_id": "CVE-2021-44228",
    })
    seen: list[str] = []

    async def fake_get(self, provider, observable):
        seen.append(observable)
        return None

    app.dependency_overrides[get_graph_store] = lambda: store
    try:
        with patch("intel_platform.enrichment.cache.EnrichmentCache.get", new=fake_get):
            resp = client.get("/api/enrichment/entities/v1", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200
    assert resp.json()["observable"] == "CVE-2021-44228"
    assert seen and set(seen) == {"CVE-2021-44228"}


def test_cached_view_reads_the_graph_off_the_event_loop(client, auth_header):
    # E-4: the sync driver call must run in a worker thread, not on the loop.
    import asyncio

    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store

    on_loop: list[bool] = []

    def get_entity(entity_id):
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)
        return {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": tp("p")}

    store = MagicMock()
    store.get_entity = get_entity
    app.dependency_overrides[get_graph_store] = lambda: store
    try:
        with patch("intel_platform.enrichment.cache.EnrichmentCache.get", new=AsyncMock(return_value=None)):
            resp = client.get("/api/enrichment/entities/e1", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    assert resp.status_code == 200
    assert on_loop == [False]


def _get_cached_view(client, auth_header, entity, cache_get):
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_graph_store

    store = MagicMock()
    store.get_entity = MagicMock(return_value=entity)
    app.dependency_overrides[get_graph_store] = lambda: store
    try:
        with patch("intel_platform.enrichment.cache.EnrichmentCache.get", new=cache_get):
            return client.get(f"/api/enrichment/entities/{entity['id']}", headers=auth_header)
    finally:
        app.dependency_overrides.pop(get_graph_store, None)


_IP = {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": tp("p")}


def test_cached_view_on_a_full_miss_is_empty(client, auth_header):
    # Contract 12: a miss used to come back as {"geoip": null, "rdap": null},
    # which the panel labelled "cached" for every provider.
    resp = _get_cached_view(client, auth_header, _IP, AsyncMock(return_value=None))
    assert resp.status_code == 200
    assert resp.json()["cached"] == {}


def test_cached_view_lists_only_providers_with_a_payload(client, auth_header):
    payload = {"properties": {"asn": "AS15169"}, "related": [], "source_url": "", "raw": {}}

    async def cache_get(self, provider, observable):
        if provider == "rdap":
            raise RuntimeError("postgres down")  # an unreadable entry is not a payload either
        return payload if provider == "geoip" else None

    resp = _get_cached_view(client, auth_header, _IP, cache_get)
    assert resp.status_code == 200
    assert resp.json()["cached"] == {"geoip": payload}


def test_admin_enrichment_get(client, auth_header):
    with patch("intel_platform.enrichment.hook.auto_enrich_enabled",
               new=AsyncMock(return_value=True)):
        resp = client.get("/api/admin/enrichment", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["auto_enabled"] is True


def test_admin_enrichment_put_persists(client, auth_header):
    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *a, **k):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            return result

        def add(self, obj):
            pass

        async def commit(self):
            pass

    with patch("intel_platform.api.routes.admin_config.get_session_factory",
               return_value=lambda: _FakeSession()):
        resp = client.put("/api/admin/enrichment", headers=auth_header, json={"auto_enabled": True})
    assert resp.status_code == 200
    assert resp.json()["auto_enabled"] is True
