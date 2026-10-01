"""Postgres bootstrap on an existing or a pgvector-less database (review, Low → G).

Two defects in `db/engine.py`, from before the schema moved to Alembic:

- `collection_sources.collection_status` shipped after the table did and was
  never added to the additive columns, the only such column not covered. A
  deployment that already had the table never got it, and every read of a
  source's status failed there. Those statements now run only while adopting a
  pre-Alembic database (`_LEGACY_ADDITIVE_COLUMNS`), and must still be right.
- `init_db` ran `CREATE EXTENSION vector` and `create_all` in one transaction,
  so a missing pgvector took the whole bootstrap down. The pgvector-less boot
  is now covered against a real Postgres in tests/test_alembic_migrations.py.
"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql

from intel_platform.db import engine as engine_module
from intel_platform.db.models import CollectionSource


class TestAdditiveColumns:
    def _statement(self) -> str:
        found = [s for s in engine_module._LEGACY_ADDITIVE_COLUMNS if "collection_status" in s]
        assert found, "collection_sources.collection_status is not backfilled"
        return found[0]

    def test_collection_status_is_backfilled(self):
        stmt = self._statement()
        assert stmt.startswith("ALTER TABLE collection_sources ADD COLUMN IF NOT EXISTS collection_status")

    def test_the_backfill_matches_the_model(self):
        """Existing rows need a value: the column is NOT NULL in the model."""
        column = CollectionSource.__table__.c.collection_status
        stmt = self._statement()
        assert column.type.compile(dialect=postgresql.dialect()) in stmt
        assert not column.nullable and "NOT NULL" in stmt
        assert f"DEFAULT '{column.default.arg}'" in stmt


class TestPlanStatus:
    def test_a_crashed_run_has_a_terminal_status(self):
        """Written when a collection run crashes (WP-E), rather than leaving
        the plan ACTIVE or marking it COMPLETED."""
        from intel_platform.db.models import CollectionPlan, PlanStatus
        assert PlanStatus.FAILED == "FAILED"
        # A plain string column, not a Postgres enum: nothing to migrate, but
        # the value must fit it.
        assert len(PlanStatus.FAILED) <= CollectionPlan.__table__.c.status.type.length
