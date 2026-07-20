"""Route tests for the enrichment API (auth + service wiring)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


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
