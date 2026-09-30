"""Postgres bootstrap on an existing or a pgvector-less database (review, Low → G).

Two defects in `db/engine.py`:

- `collection_sources.collection_status` shipped after the table did and was
  never added to `_ADDITIVE_COLUMNS`, the only such column not covered. A
  deployment that already had the table never got it, and every read of a
  source's status failed there.
- `init_db` ran `CREATE EXTENSION vector` and `create_all` in one transaction.
  When pgvector is missing the extension statement fails, Postgres aborts the
  transaction, and `create_all` then fails too — so the "vector search
  disabled" warning was followed by a crash, and even a separate transaction
  could not help while the vector tables were still in the create list.

No Postgres is needed: the fake engine below models the one Postgres rule that
matters — after a failed statement, the transaction refuses everything else.
"""
from __future__ import annotations

import logging

import pytest
from sqlalchemy.dialects import postgresql

from intel_platform.db import engine as engine_module
from intel_platform.db.models import Base, CollectionSource

VECTOR_TABLES = {"chunk_embeddings", "attack_technique_embeddings"}


class TestAdditiveColumns:
    def _statement(self) -> str:
        found = [s for s in engine_module._ADDITIVE_COLUMNS if "collection_status" in s]
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


class _Transaction:
    def __init__(self, engine):
        self.engine = engine
        self.aborted = False
        self.statements: list[str] = []

    async def __aenter__(self):
        return _Connection(self)

    async def __aexit__(self, *exc):
        return False


class _Connection:
    def __init__(self, tx: _Transaction):
        self._tx = tx

    def _check(self):
        if self._tx.aborted:
            raise RuntimeError("current transaction is aborted, commands ignored until end of transaction block")

    async def execute(self, statement):
        self._check()
        sql = str(statement)
        self._tx.statements.append(sql)
        if "CREATE EXTENSION" in sql and not self._tx.engine.has_vector:
            self._tx.aborted = True
            raise RuntimeError('extension "vector" is not available')

        class _Result:
            rowcount = 0
        return _Result()

    async def run_sync(self, fn, *args, **kwargs):
        self._check()
        self._tx.statements.append("create_all")
        return fn(object(), *args, **kwargs)


class _Engine:
    def __init__(self, has_vector: bool):
        self.has_vector = has_vector
        self.transactions: list[_Transaction] = []

    def begin(self):
        tx = _Transaction(self)
        self.transactions.append(tx)
        return tx


@pytest.fixture
def created(monkeypatch):
    """Patch the engine and record which tables create_all was asked for."""
    calls: list[set[str]] = []

    def fake_create_all(bind, tables=None, **_kwargs):
        chosen = tables if tables is not None else Base.metadata.sorted_tables
        calls.append({t.name for t in chosen})

    monkeypatch.setattr(Base.metadata, "create_all", fake_create_all)

    def use(has_vector: bool) -> _Engine:
        engine = _Engine(has_vector)
        monkeypatch.setattr(engine_module, "get_engine", lambda: engine)
        return engine

    return use, calls


class TestInitDbWithoutPgvector:
    async def test_it_completes(self, created):
        use, calls = created
        use(has_vector=False)
        await engine_module.init_db()
        assert calls, "create_all never ran"

    async def test_the_extension_has_a_transaction_of_its_own(self, created):
        use, _calls = created
        engine = use(has_vector=False)
        await engine_module.init_db()
        ext_tx = next(t for t in engine.transactions if any("CREATE EXTENSION" in s for s in t.statements))
        assert "create_all" not in ext_tx.statements

    async def test_every_table_but_the_vector_ones_is_created(self, created, caplog):
        use, calls = created
        use(has_vector=False)
        with caplog.at_level(logging.WARNING, logger="intel_platform.db.engine"):
            await engine_module.init_db()
        (tables,) = calls
        assert not tables & VECTOR_TABLES
        assert "collection_sources" in tables and "pirs" in tables
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert all(name in logged for name in VECTOR_TABLES), "skipped tables must be named"


class TestPlanStatus:
    def test_a_crashed_run_has_a_terminal_status(self):
        """Written when a collection run crashes (WP-E), rather than leaving
        the plan ACTIVE or marking it COMPLETED."""
        from intel_platform.db.models import CollectionPlan, PlanStatus
        assert PlanStatus.FAILED == "FAILED"
        # A plain string column, not a Postgres enum: nothing to migrate, but
        # the value must fit it.
        assert len(PlanStatus.FAILED) <= CollectionPlan.__table__.c.status.type.length


class TestInitDbWithPgvector:
    async def test_every_table_is_created(self, created):
        use, calls = created
        use(has_vector=True)
        await engine_module.init_db()
        (tables,) = calls
        assert VECTOR_TABLES <= tables
