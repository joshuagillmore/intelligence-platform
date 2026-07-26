"""Route tests for the ATT&CK API (auth + admin gating + wiring).

Graph work is mocked here (covered end-to-end in ``test_attack_graph.py``); the
Neo4j driver dependency is overridden so no DB is needed.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from intel_platform.api.app import app
    return TestClient(app)


@pytest.fixture
def admin_header():
    from intel_platform.api.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


@pytest.fixture
def analyst_header():
    from intel_platform.api.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token('bob', 'analyst')}"}


@pytest.fixture(autouse=True)
def _override_driver():
    from intel_platform.api.app import app
    from intel_platform.api.deps import get_neo4j_driver

    app.dependency_overrides[get_neo4j_driver] = lambda: MagicMock()
    yield
    app.dependency_overrides.pop(get_neo4j_driver, None)


def test_status_requires_auth(client):
    resp = client.get("/api/attack/status")
    assert resp.status_code in (401, 403)


def test_status_shape(client, analyst_header):
    fake = {"ingested": False, "version": None,
            "counts": {"tactics": 0, "techniques": 0, "groups": 0, "software": 0, "mitigations": 0}}
    with patch("intel_platform.services.attack.graph_ops.attack_status", return_value=fake):
        resp = client.get("/api/attack/status", headers=analyst_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingested"] is False
    assert set(body["counts"]) == {"tactics", "techniques", "groups", "software", "mitigations"}


def test_ingest_requires_admin(client, analyst_header):
    resp = client.post("/api/attack/ingest", headers=analyst_header)
    assert resp.status_code == 403


def test_ingest_admin_returns_counts(client, admin_header):
    fake = {"version": "19.1", "counts": {"tactics": 14, "techniques": 200,
                                          "groups": 150, "software": 700, "mitigations": 43}}
    with patch("intel_platform.api.routes.attack.fetch_and_ingest",
               new=AsyncMock(return_value=fake)):
        resp = client.post("/api/attack/ingest", headers=admin_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingested"] is True
    assert body["version"] == "19.1"
    assert body["counts"]["techniques"] == 200


def test_ingest_failure_is_502_without_leaking(client, admin_header):
    with patch("intel_platform.api.routes.attack.fetch_and_ingest",
               new=AsyncMock(side_effect=RuntimeError("boom: secret url"))):
        resp = client.post("/api/attack/ingest", headers=admin_header)
    assert resp.status_code == 502
    assert "boom" not in resp.text


def test_resolve_returns_mapped(client, analyst_header):
    with patch("intel_platform.services.attack.graph_ops.resolve_ttps", return_value={"mapped": 7}):
        resp = client.post("/api/attack/resolve", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 200
    assert resp.json() == {"mapped": 7}


def test_ingest_vuln_chain_requires_admin(client, analyst_header):
    resp = client.post("/api/attack/ingest-vuln-chain", headers=analyst_header)
    assert resp.status_code == 403


def test_ingest_vuln_chain_admin_returns_counts(client, admin_header):
    with patch("intel_platform.api.routes.attack.vuln_chain.ingest_vuln_chain",
               new=AsyncMock(return_value={"cwes": 900, "edges": 1500})):
        resp = client.post("/api/attack/ingest-vuln-chain", headers=admin_header)
    assert resp.status_code == 200
    assert resp.json() == {"cwes": 900, "edges": 1500}


def test_ingest_vuln_chain_failure_is_502_without_leaking(client, admin_header):
    with patch("intel_platform.api.routes.attack.vuln_chain.ingest_vuln_chain",
               new=AsyncMock(side_effect=RuntimeError("boom: secret url"))):
        resp = client.post("/api/attack/ingest-vuln-chain", headers=admin_header)
    assert resp.status_code == 502
    assert "boom" not in resp.text


def test_resolve_cve_returns_counts(client, analyst_header):
    with patch("intel_platform.services.attack.vuln_chain.resolve_cve",
               return_value={"vulnerabilities": 4, "techniques_linked": 11}):
        resp = client.post("/api/attack/resolve-cve", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 200
    assert resp.json() == {"vulnerabilities": 4, "techniques_linked": 11}


def test_matrix_passthrough(client, analyst_header):
    fake = {"version": "19.1", "ingested": True, "tactics": []}
    with patch("intel_platform.services.attack.graph_ops.get_matrix", return_value=fake):
        resp = client.get("/api/attack/matrix", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 200
    assert resp.json()["ingested"] is True


def test_technique_404(client, analyst_header):
    with patch("intel_platform.services.attack.graph_ops.get_technique", return_value=None):
        resp = client.get("/api/attack/technique/T9999", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 404


def test_navigator_layer_is_attachment(client, analyst_header):
    fake = {"name": "x", "versions": {"layer": "4.5"}, "techniques": []}
    with patch("intel_platform.services.attack.graph_ops.navigator_layer", return_value=fake):
        resp = client.get("/api/attack/navigator-layer", params={"project_id": "abcdef12"}, headers=analyst_header)
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")


@pytest.fixture
def _override_db():
    """Override the Postgres session dependency for the embed/map routes."""
    from intel_platform.api.app import app
    from intel_platform.db.engine import get_db

    session = MagicMock()
    session.commit = AsyncMock()
    app.dependency_overrides[get_db] = lambda: session
    yield
    app.dependency_overrides.pop(get_db, None)


def test_embed_requires_admin(client, analyst_header, _override_db):
    resp = client.post("/api/attack/embed", headers=analyst_header)
    assert resp.status_code == 403


def test_embed_admin_returns_count(client, admin_header, _override_db):
    with patch("intel_platform.api.routes.attack.attack_embeddings.embed_techniques",
               new=AsyncMock(return_value=697)):
        resp = client.post("/api/attack/embed", headers=admin_header)
    assert resp.status_code == 200
    assert resp.json() == {"embedded": 697}


def test_map_returns_counts(client, analyst_header, _override_db):
    with patch("intel_platform.api.routes.attack.attack_mapping.map_project_ttps",
               new=AsyncMock(return_value={"mapped": 3, "skipped": 2})):
        resp = client.post("/api/attack/map", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 200
    assert resp.json() == {"mapped": 3, "skipped": 2}


def test_d3fend_requires_auth(client):
    resp = client.get("/api/attack/technique/T1566/d3fend")
    assert resp.status_code in (401, 403)


def test_d3fend_passthrough(client, analyst_header, _override_db):
    fake = {"countermeasures": [{"id": "d3f:FileHashing", "label": "File Hashing"}]}
    with patch("intel_platform.api.routes.attack.attack_d3fend.get_countermeasures",
               new=AsyncMock(return_value=fake)):
        resp = client.get("/api/attack/technique/T1566/d3fend", headers=analyst_header)
    assert resp.status_code == 200
    assert resp.json() == fake


def test_report_requires_auth(client):
    resp = client.get("/api/attack/report", params={"project_id": "p1"})
    assert resp.status_code in (401, 403)


def test_report_passthrough(client, analyst_header):
    fake = {"project_id": "p1", "observed_by_tactic": [], "attribution": [],
            "key_mitigations": [], "cve_enabled": [], "narrative": None, "markdown": "# x\n"}
    with patch("intel_platform.api.routes.attack.attack_report.build_report",
               new=AsyncMock(return_value=fake)):
        resp = client.get("/api/attack/report", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# x\n"


def test_report_failure_is_500_without_leaking(client, analyst_header):
    with patch("intel_platform.api.routes.attack.attack_report.build_report",
               new=AsyncMock(side_effect=RuntimeError("boom: secret detail"))):
        resp = client.get("/api/attack/report", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 500
    assert "boom" not in resp.text


def test_attribution_passthrough(client, analyst_header):
    fake = {"observed_total": 2, "groups": [{"id": "G0001", "name": "GroupAlpha",
            "shared_count": 2, "coverage": 1.0, "shared_techniques": []}]}
    with patch("intel_platform.services.attack.graph_ops.get_attribution", return_value=fake):
        resp = client.get("/api/attack/attribution", params={"project_id": "p1"}, headers=analyst_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed_total"] == 2
    assert body["groups"][0]["id"] == "G0001"


def test_embed_zero_reports_why(client, admin_header, _override_db):
    """A bare {"embedded": 0} reads as "already done".

    Found live: a trial Cohere key rate-limited the 695-technique catalogue, the
    route returned 200 with {"embedded": 0}, and ATT&CK mapping then silently
    matched nothing because the catalogue was never embedded.
    """
    from intel_platform.services.attack import embeddings as attack_embeddings

    async def _fail(*a, **kw):
        attack_embeddings.last_failure_reason = "embedding_provider_rate_limited"
        return 0

    with patch("intel_platform.api.routes.attack.attack_embeddings.embed_techniques", new=_fail):
        resp = client.post("/api/attack/embed", headers=admin_header)

    assert resp.status_code == 200
    body = resp.json()
    assert body["embedded"] == 0
    assert body["reason"] == "embedding_provider_rate_limited"
    assert "Retry later" in body["detail"]


def test_embed_success_has_no_reason(client, admin_header, _override_db):
    from intel_platform.services.attack import embeddings as attack_embeddings

    async def _ok(*a, **kw):
        attack_embeddings.last_failure_reason = ""
        return 695

    with patch("intel_platform.api.routes.attack.attack_embeddings.embed_techniques", new=_ok):
        body = client.post("/api/attack/embed", headers=admin_header).json()

    assert body == {"embedded": 695}
