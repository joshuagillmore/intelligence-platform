"""Tests for the auto-enrich hook — the AppSetting gate and target filtering."""
import asyncio
from unittest.mock import MagicMock

from intel_platform.enrichment import hook


def _factory_with_value(value):
    class _Result:
        def scalar_one_or_none(self):
            return value

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *a, **k):
            return _Result()

    return lambda: _Session()


async def test_auto_enrich_enabled_true(monkeypatch):
    import intel_platform.db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_session_factory", lambda: _factory_with_value("true"))
    assert await hook.auto_enrich_enabled() is True


async def test_auto_enrich_disabled_by_default(monkeypatch):
    import intel_platform.db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_session_factory", lambda: _factory_with_value(None))
    assert await hook.auto_enrich_enabled() is False


async def test_auto_enrich_failsafe_on_db_error(monkeypatch):
    import intel_platform.db.engine as engine_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(engine_mod, "get_session_factory", _boom)
    assert await hook.auto_enrich_enabled() is False


async def test_schedule_skips_non_cyber(monkeypatch):
    called = {"v": False}

    async def _spy(store, targets):
        called["v"] = True

    monkeypatch.setattr(hook, "_run_auto_enrich", _spy)
    hook.schedule_auto_enrich(MagicMock(), [{"id": "1", "entity_type": "Person"}])
    await asyncio.sleep(0.01)
    assert called["v"] is False


async def test_schedule_runs_for_cyber_targets_only(monkeypatch):
    captured = {"targets": None}

    async def _spy(store, targets):
        captured["targets"] = targets

    monkeypatch.setattr(hook, "_run_auto_enrich", _spy)
    hook.schedule_auto_enrich(MagicMock(), [
        {"id": "1", "entity_type": "IPAddress"},
        {"id": "2", "entity_type": "Person"},
    ])
    await asyncio.sleep(0.01)
    assert captured["targets"] is not None
    assert [t["id"] for t in captured["targets"]] == ["1"]  # only the cyber node
