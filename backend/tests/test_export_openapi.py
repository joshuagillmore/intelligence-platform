"""backend/openapi.json is the API's schema, current and reproducible (contract 9).

The frontend generates its types from the committed file, so it must change
exactly when the API does. A route or model change without a regenerated file
fails here: run `uv run python scripts/export_openapi.py` from backend/.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from intel_platform.api.app import app

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"
_spec = importlib.util.spec_from_file_location("export_openapi", _SCRIPT)
export_openapi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_openapi)


def test_the_output_is_reproducible_and_sorted():
    first = export_openapi.schema_text(app)
    assert first == export_openapi.schema_text(app)
    assert first.endswith("\n")
    top = list(json.loads(first))
    assert top == sorted(top)


def test_the_committed_file_is_current():
    committed = export_openapi.OUTPUT.read_text(encoding="utf-8")
    assert committed == export_openapi.schema_text(app), (
        "backend/openapi.json is stale: run `uv run python scripts/export_openapi.py` from backend/"
    )


def test_the_contract_shapes_are_in_it():
    schema = json.loads(export_openapi.OUTPUT.read_text(encoding="utf-8"))
    paths, components = schema["paths"], schema["components"]["schemas"]
    assert {"/api/auth/me", "/api/auth/logout", "/api/admin/degraded"} <= set(paths)
    login = paths["/api/auth/login"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert "access_token" not in components[login.rsplit("/", 1)[-1]]["properties"]
    health = paths["/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert "degraded" in components[health.rsplit("/", 1)[-1]]["properties"]
    form = paths["/api/ingest"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    assert "source_name" in components[form.rsplit("/", 1)[-1]]["properties"]
    assert "project_id" in [p["name"] for p in paths["/api/reports/{report_id}"]["get"]["parameters"]]
