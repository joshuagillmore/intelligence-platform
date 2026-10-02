"""Under tests the engine must not pool: the sync TestClient runs every request
on a fresh event loop, and an asyncpg connection pooled on a closed loop fails
the next route that reuses it (seen in CI as "cannot rollback; the transaction
is in error state" on the topic tree)."""
from sqlalchemy.pool import NullPool

from intel_platform.db import engine as engine_module


def test_engine_uses_a_null_pool_when_asked(monkeypatch):
    from intel_platform.config import get_settings

    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(engine_module, "_session_factory", None)
    monkeypatch.setattr(get_settings(), "postgres_null_pool", True)
    eng = engine_module.get_engine()
    assert isinstance(eng.pool, NullPool)
    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(get_settings(), "postgres_null_pool", False)
    assert not isinstance(engine_module.get_engine().pool, NullPool)
    monkeypatch.setattr(engine_module, "_engine", None)
