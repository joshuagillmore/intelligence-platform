"""Tests for the PIR (Priority Intelligence Requirement) spine.

The PIR routes are Postgres-backed and the suite has no Postgres (only Neo4j —
see backend/CLAUDE.md), so these exercise the handlers directly against a fake
AsyncSession, plus the pure validation/serialization helpers. That covers the
logic that is actually ours: validation, title derivation, PIR→plan linking and
the reuse/create decision in get_or_create_pir.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from intel_platform.api.routes.collection_plans import _plan_to_dict
from intel_platform.api.routes.pirs import (
    _pir_to_response,
    _plan_link,
    _validate_priority,
    _validate_status,
    create_pir,
    derive_title,
    get_or_create_pir,
)
from intel_platform.db.models import PIR_PRIORITIES, PIR_STATUSES, CollectionPlan, Pir, PirStatus
from intel_platform.models.requests import CreatePirRequest


# ---------------------------------------------------------------------------
# Fake AsyncSession — just enough surface for the PIR handlers
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Records writes and replays canned query results."""

    def __init__(self, get_result=None, query_rows: list | None = None):
        self._get_result = get_result
        self._query_rows = query_rows or []
        self.added: list = []
        self.deleted: list = []
        self.executed: list = []
        self.commits = 0
        self.flushes = 0

    async def get(self, _model, _pk):
        return self._get_result

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _FakeResult(self._query_rows)

    def add(self, obj):
        # Stand in for the server-side column defaults so serialization sees a
        # persisted-looking row.
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        obj.created_at = obj.created_at or now
        obj.updated_at = obj.updated_at or now
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _make_pir(**kwargs) -> Pir:
    defaults = dict(
        id=uuid.uuid4(),
        project_id="test-proj",
        title="Actor infrastructure",
        text="What infrastructure does APT-29 use for C2?",
        refined_text="",
        eeis=[],
        priority="high",
        status=PirStatus.OPEN,
        created_by="analyst",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Pir(**defaults)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_status_vocabulary(self):
        assert PIR_STATUSES == ("OPEN", "PARTIAL", "SATISFIED", "ARCHIVED")
        for status in PIR_STATUSES:
            assert _validate_status(status) == status

    def test_invalid_status_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_status("DONE")
        assert exc.value.status_code == 400

    def test_priority_vocabulary(self):
        assert PIR_PRIORITIES == ("critical", "high", "medium", "low")
        for priority in PIR_PRIORITIES:
            assert _validate_priority(priority) == priority

    def test_invalid_priority_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_priority("URGENT")
        assert exc.value.status_code == 400

    def test_derive_title_collapses_whitespace(self):
        assert derive_title("  What   does\nAPT-29 target? ") == "What does APT-29 target?"

    def test_derive_title_truncates_long_text(self):
        title = derive_title("x" * 400)
        assert len(title) <= 120
        assert title.endswith("...")


# ---------------------------------------------------------------------------
# Serialization — PIR carries the plans it drove
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_pir_response_without_plans(self):
        pir = _make_pir()
        resp = _pir_to_response(pir)
        assert resp.id == str(pir.id)
        assert resp.status == "OPEN"
        assert resp.priority == "high"
        assert resp.plan_count == 0
        assert resp.plans == []

    def test_pir_response_includes_plan_links(self):
        pir = _make_pir()
        plan = CollectionPlan(
            id=uuid.uuid4(), project_id="test-proj", name="PIR: C2 infrastructure",
            status="ACTIVE", pir_id=pir.id, created_at=datetime.now(timezone.utc),
        )
        resp = _pir_to_response(pir, [plan])
        assert resp.plan_count == 1
        assert resp.plans[0].id == str(plan.id)
        assert resp.plans[0].status == "ACTIVE"
        assert resp.plans[0].source_count == 0
        assert resp.plans[0].records_acquired == 0

    def test_plan_link_aggregates_source_records(self):
        from intel_platform.db.models import CollectionSource

        plan = CollectionPlan(id=uuid.uuid4(), project_id="test-proj", name="p", status="ACTIVE")
        plan.sources = [
            CollectionSource(name="a", source_type="web_scrape", total_records_acquired=3),
            CollectionSource(name="b", source_type="rss_feed", total_records_acquired=4),
        ]
        link = _plan_link(plan)
        assert link.source_count == 2
        assert link.records_acquired == 7

    def test_plan_dict_exposes_pir_id(self):
        pir_id = uuid.uuid4()
        plan = CollectionPlan(id=uuid.uuid4(), project_id="test-proj", name="p",
                              status="DRAFT", pir_id=pir_id)
        assert _plan_to_dict(plan)["pir_id"] == str(pir_id)

        unlinked = CollectionPlan(id=uuid.uuid4(), project_id="test-proj", name="p", status="DRAFT")
        assert _plan_to_dict(unlinked)["pir_id"] is None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

class TestCreatePir:
    async def test_create_persists_and_derives_title(self):
        db = FakeSession()
        resp = await create_pir(
            CreatePirRequest(project_id="test-proj", text="  Where is APT-29 staging?  "),
            db=db,
        )
        assert db.commits == 1
        assert len(db.added) == 1
        assert resp.text == "Where is APT-29 staging?"
        assert resp.title == "Where is APT-29 staging?"
        assert resp.status == "OPEN"
        assert resp.priority == "medium"

    async def test_create_rejects_blank_text(self):
        with pytest.raises(HTTPException) as exc:
            await create_pir(CreatePirRequest(project_id="test-proj", text="   "), db=FakeSession())
        assert exc.value.status_code == 400

    async def test_create_rejects_bad_status(self):
        with pytest.raises(HTTPException) as exc:
            await create_pir(
                CreatePirRequest(project_id="test-proj", text="q", status="NOPE"), db=FakeSession()
            )
        assert exc.value.status_code == 400

    async def test_create_drops_empty_eeis(self):
        resp = await create_pir(
            CreatePirRequest(project_id="test-proj", text="q", eeis=["a", "", "  ", "b"]),
            db=FakeSession(),
        )
        assert resp.eeis == ["a", "b"]


class TestGetOrCreatePir:
    async def test_resolves_existing_by_id(self):
        pir = _make_pir()
        db = FakeSession(get_result=pir)
        resolved = await get_or_create_pir(db, "test-proj", "", pir_id=str(pir.id))
        assert resolved is pir
        assert db.added == []

    async def test_unknown_id_is_404(self):
        with pytest.raises(HTTPException) as exc:
            await get_or_create_pir(FakeSession(get_result=None), "test-proj", "", pir_id=str(uuid.uuid4()))
        assert exc.value.status_code == 404

    async def test_cross_project_id_is_400(self):
        pir = _make_pir(project_id="other-proj")
        with pytest.raises(HTTPException) as exc:
            await get_or_create_pir(FakeSession(get_result=pir), "test-proj", "", pir_id=str(pir.id))
        assert exc.value.status_code == 400

    async def test_malformed_id_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await get_or_create_pir(FakeSession(), "test-proj", "", pir_id="not-a-uuid")
        assert exc.value.status_code == 400

    async def test_blank_text_without_id_anchors_nothing(self):
        db = FakeSession()
        assert await get_or_create_pir(db, "test-proj", "   ") is None
        assert db.added == []

    async def test_free_text_creates_a_requirement(self):
        db = FakeSession(query_rows=[])
        pir = await get_or_create_pir(db, "test-proj", "  Who funds the network?  ")
        assert pir is not None
        assert pir.text == "Who funds the network?"
        assert pir.title == "Who funds the network?"
        assert pir.status == PirStatus.OPEN
        assert db.added == [pir]
        assert db.flushes == 1

    async def test_identical_live_text_is_reused_not_duplicated(self):
        existing = _make_pir(text="Who funds the network?")
        db = FakeSession(query_rows=[existing])
        pir = await get_or_create_pir(db, "test-proj", "Who funds the network?")
        assert pir is existing
        assert db.added == []


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def test_pir_routes_registered():
    from intel_platform.api.app import app

    paths = {route.path for route in app.routes}
    assert "/api/pirs" in paths
    assert "/api/pirs/{pir_id}" in paths


def test_pir_column_backfill_registered():
    """Existing databases only gain collection_plans.pir_id via the additive
    migration — create_all never ALTERs a table that already exists."""
    from intel_platform.db.engine import _ADDITIVE_COLUMNS

    joined = " ".join(_ADDITIVE_COLUMNS)
    assert "ALTER TABLE collection_plans ADD COLUMN IF NOT EXISTS pir_id UUID" in joined
