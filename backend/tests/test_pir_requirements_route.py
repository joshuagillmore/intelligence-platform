"""GET /pirs/{id}/requirements — per-element collection state.

The assessor's reasoning about *why* a requirement is unfinished was computed
and then discarded into a response nothing consumed. These rows are what the
collection loop acts on, so this is the endpoint that makes the loop's decisions
inspectable: which elements were answered, which were tried and given up on, and
what each one is still missing.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from intel_platform.db.models import PirRequirement


@pytest.fixture
def client():
    from intel_platform.api.app import app

    return TestClient(app)


@pytest.fixture
def analyst_header():
    from intel_platform.api.auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token('bob', 'analyst')}"}


def _row(ordinal, text, status="pending", attempts=0, missing="", confidence=""):
    row = PirRequirement(pir_id=uuid.uuid4(), project_id="p1", ordinal=ordinal, text=text)
    row.status = status
    row.attempts = attempts
    row.next_queries = ["tried query"] if attempts else []
    row.assessment_missing = missing
    row.assessment_confidence = confidence
    return row


@pytest.fixture
def fake_pir():
    return SimpleNamespace(
        id=uuid.uuid4(), project_id="p1",
        eeis=["Which vessels?", "On what dates?", "What tactics?"],
    )


def _install(rows, pir):
    """Wire a session whose reads return `rows` and whose sync is a no-op."""
    from intel_platform.api.app import app
    from intel_platform.db.engine import get_db

    session = MagicMock()
    session.get = AsyncMock(return_value=pir)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: list(rows))
        )
    )
    app.dependency_overrides[get_db] = lambda: session
    return session


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from intel_platform.api.app import app
    from intel_platform.db.engine import get_db

    app.dependency_overrides.pop(get_db, None)


def test_requires_auth(client, fake_pir):
    _install([], fake_pir)
    assert client.get(f"/api/pirs/{fake_pir.id}/requirements").status_code in (401, 403)


def test_unknown_pir_is_404(client, analyst_header):
    _install([], None)
    r = client.get(f"/api/pirs/{uuid.uuid4()}/requirements", headers=analyst_header)
    assert r.status_code == 404


def test_elements_are_returned_in_order(client, analyst_header, fake_pir):
    rows = [_row(0, "Which vessels?"), _row(1, "On what dates?"), _row(2, "What tactics?")]
    _install(rows, fake_pir)
    body = client.get(f"/api/pirs/{fake_pir.id}/requirements", headers=analyst_header).json()
    assert [e["ordinal"] for e in body["elements"]] == [0, 1, 2]
    assert body["total"] == 3


def test_tried_and_untried_are_distinguishable(client, analyst_header, fake_pir):
    """'unmet' means tried and given up on; 'pending' means still open. An
    analyst deciding whether to collect more needs to tell them apart.

    Row text matches the PIR's elements: sync deliberately resets the state of a
    re-worded element, so a mismatched fixture would be testing that reset.
    """
    rows = [
        _row(0, fake_pir.eeis[0], status="satisfied"),
        _row(1, fake_pir.eeis[1], status="unmet", attempts=2, missing="no dates found"),
        _row(2, fake_pir.eeis[2], status="pending"),
    ]
    _install(rows, fake_pir)
    body = client.get(f"/api/pirs/{fake_pir.id}/requirements", headers=analyst_header).json()

    assert body["counts"] == {"pending": 1, "satisfied": 1, "unmet": 1}
    retired = [e for e in body["elements"] if e["status"] == "unmet"][0]
    assert retired["attempts"] == 2
    assert retired["missing"] == "no dates found"


def test_the_assessors_reasoning_is_exposed(client, analyst_header, fake_pir):
    fake_pir.eeis = ["a?"]
    rows = [_row(0, "a?", status="unmet", attempts=2,
                 missing="enrichment percentages absent", confidence="high")]
    _install(rows, fake_pir)
    body = client.get(f"/api/pirs/{fake_pir.id}/requirements", headers=analyst_header).json()
    element = body["elements"][0]
    assert element["missing"] == "enrichment percentages absent"
    assert element["confidence"] == "high"
    assert element["queries_tried"] == ["tried query"]


def test_a_pir_with_no_elements_reports_zero_not_an_error(client, analyst_header, fake_pir):
    fake_pir.eeis = []
    _install([], fake_pir)
    r = client.get(f"/api/pirs/{fake_pir.id}/requirements", headers=analyst_header)
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["counts"] == {"pending": 0, "satisfied": 0, "unmet": 0}
