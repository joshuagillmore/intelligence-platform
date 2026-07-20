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


async def test_schedule_hands_off_to_passed_loop_when_no_running_loop(monkeypatch):
    # Simulate the plan_executor worker-thread path: no running loop, but a loop
    # was passed -> hand the coroutine over via run_coroutine_threadsafe.
    def _no_loop(*a, **k):
        raise RuntimeError("no running loop")

    scheduled = []

    def _threadsafe(coro, loop):
        scheduled.append(loop)
        coro.close()  # avoid "coroutine was never awaited"

    monkeypatch.setattr(hook.asyncio, "get_running_loop", _no_loop)
    monkeypatch.setattr(hook.asyncio, "run_coroutine_threadsafe", _threadsafe)

    fake_loop = MagicMock()
    hook.schedule_auto_enrich(MagicMock(), [{"id": "1", "entity_type": "Domain"}], loop=fake_loop)
    assert scheduled == [fake_loop]


async def test_schedule_no_loop_no_handoff_is_noop(monkeypatch):
    def _no_loop(*a, **k):
        raise RuntimeError("no running loop")

    calls = []
    monkeypatch.setattr(hook.asyncio, "get_running_loop", _no_loop)
    monkeypatch.setattr(hook.asyncio, "run_coroutine_threadsafe",
                        lambda *a, **k: calls.append(1))
    # No running loop and no passed loop -> clean no-op, nothing scheduled.
    hook.schedule_auto_enrich(MagicMock(), [{"id": "1", "entity_type": "Domain"}])
    assert calls == []
