import copy

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.auth import create_access_token
from intel_platform.api.routes import personas as personas_route
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture(autouse=True)
def _isolated_personas(monkeypatch):
    """Personas are process-global; every test here gets its own copy.

    Changes are persisted to Postgres (AppSetting) before they apply; that is
    covered in test_persisted_settings.py, so here the save always succeeds.
    """
    monkeypatch.setattr(personas_route, "_personas", copy.deepcopy(personas_route._personas))
    monkeypatch.setattr(personas_route, "_active_persona", personas_route._active_persona)

    async def _saved(values):
        return None

    monkeypatch.setattr(personas_route, "_persist", _saved)


def test_list_personas():
    resp = client.get("/api/personas", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["personas"]) >= 4
    assert data["active_persona"]

def test_activate_persona():
    resp = client.post("/api/personas/cyber_analyst/activate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["active_persona"] == "cyber_analyst"


# ---------------------------------------------------------------------------
# Contract 13: the active persona shapes every user's PIR decomposition, so
# changing personas is an admin action, and built-ins cannot be overwritten.
# ---------------------------------------------------------------------------

ANALYST = {"Authorization": f"Bearer {create_access_token('analyst-p', role='analyst')}"}
ADMIN = {"Authorization": f"Bearer {create_access_token('admin-p', role='admin')}"}
CUSTOM = {"id": "maritime", "name": "Maritime Analyst", "description": "Shipping and ports", "skills": ["gap_analysis"]}


class TestAnalystsCannotChangePersonas:
    def test_create(self):
        assert client.post("/api/personas", json=CUSTOM, headers=ANALYST).status_code == 403
        assert "maritime" not in personas_route._personas

    def test_activate(self):
        before = personas_route._active_persona
        assert client.post("/api/personas/cyber_analyst/activate", headers=ANALYST).status_code == 403
        assert personas_route._active_persona == before

    def test_delete(self):
        personas_route._personas["maritime"] = {**CUSTOM, "temperature": 0.3, "active": False}
        assert client.delete("/api/personas/maritime", headers=ANALYST).status_code == 403
        assert "maritime" in personas_route._personas

    def test_reading_is_still_allowed(self):
        assert client.get("/api/personas", headers=ANALYST).status_code == 200
        assert client.get("/api/personas/active", headers=ANALYST).status_code == 200


class TestAdminsCan:
    def test_create_activate_and_delete(self):
        assert client.post("/api/personas", json=CUSTOM, headers=ADMIN).status_code == 200
        assert client.post("/api/personas/maritime/activate", headers=ADMIN).status_code == 200
        assert personas_route._active_persona == "maritime"
        client.post("/api/personas/allsource/activate", headers=ADMIN)
        assert client.delete("/api/personas/maritime", headers=ADMIN).status_code == 200

    def test_update_a_custom_persona(self):
        client.post("/api/personas", json=CUSTOM, headers=ADMIN)
        resp = client.post("/api/personas", json={**CUSTOM, "description": "Revised"}, headers=ADMIN)
        assert resp.status_code == 200
        assert personas_route._personas["maritime"]["description"] == "Revised"


@pytest.mark.parametrize("builtin", ["osint_collector", "cyber_analyst", "allsource", "report_writer"])
def test_a_builtin_id_cannot_be_overwritten(builtin):
    original = copy.deepcopy(personas_route._personas[builtin])
    resp = client.post("/api/personas", json={**CUSTOM, "id": builtin}, headers=ADMIN)
    assert resp.status_code == 409
    assert personas_route._personas[builtin] == original
