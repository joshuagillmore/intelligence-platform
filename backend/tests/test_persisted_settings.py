"""Personas and the admin LLM override survive a restart (WP-P task 3).

Both were process memory: a restart reset the admin's provider choice to the
configured default and dropped every custom persona and the active selection.
They are now AppSetting rows, read at startup (init_db's loaders) and by any
other process through `refresh_persisted_settings()`; the in-memory dicts are
the cache. Built-in personas still cannot be overwritten, by a request or by a
row someone edited.

Runs against a scratch database (tests/pg.py); skips without Postgres.
"""
from __future__ import annotations

import copy
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from intel_platform.api.routes import admin_config
from intel_platform.api.routes import personas
from intel_platform.db import engine as engine_module
from tests.pg import pg_engine, scratch_pg_url  # noqa: F401


@pytest.fixture
async def migrated(pg_engine, monkeypatch):  # noqa: F811
    """A migrated scratch schema, with the persona and override caches isolated."""
    monkeypatch.setattr(personas, "_personas", copy.deepcopy(personas._BUILTIN_PERSONAS))
    monkeypatch.setattr(personas, "_active_persona", personas._DEFAULT_ACTIVE)
    monkeypatch.setattr(admin_config, "_llm_override", {"provider": "", "model": ""})
    await engine_module.init_db()
    return pg_engine


def _restart(monkeypatch):
    """Lose the in-memory state, as a process restart does."""
    monkeypatch.setattr(personas, "_personas", copy.deepcopy(personas._BUILTIN_PERSONAS))
    monkeypatch.setattr(personas, "_active_persona", personas._DEFAULT_ACTIVE)
    monkeypatch.setattr(admin_config, "_llm_override", {"provider": "", "model": ""})


async def _row(engine, key: str) -> str | None:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key})).scalar_one_or_none()


CUSTOM = personas.PersonaRequest(
    id="maritime", name="Maritime Analyst", description="Shipping and ports", skills=["gap_analysis"], temperature=0.2,
)


class TestLlmOverride:
    async def test_a_selection_is_persisted(self, migrated):
        await admin_config.select_llm(admin_config.LLMConfigRequest(provider="ollama", model="qwen2.5:14b"))
        stored = json.loads(await _row(migrated, admin_config.LLM_OVERRIDE_KEY))
        assert stored == {"provider": "ollama", "model": "qwen2.5:14b"}

    async def test_it_survives_a_restart(self, migrated, monkeypatch):
        await admin_config.select_llm(admin_config.LLMConfigRequest(provider="ollama", model="qwen2.5:14b"))
        _restart(monkeypatch)
        assert admin_config.get_llm_override() is None
        await admin_config.refresh_persisted_settings()
        assert admin_config.get_llm_override() == {"provider": "ollama", "model": "qwen2.5:14b"}
        assert admin_config.get_active_provider() == "ollama"

    async def test_init_db_loads_it(self, migrated, monkeypatch):
        await admin_config.select_llm(admin_config.LLMConfigRequest(provider="cohere", model=""))
        _restart(monkeypatch)
        await engine_module.init_db()
        assert admin_config.get_active_provider() == "cohere"

    async def test_no_row_leaves_the_configured_default(self, migrated):
        await admin_config.refresh_persisted_settings()
        assert admin_config.get_llm_override() is None

    async def test_a_failed_save_changes_nothing(self, migrated, monkeypatch):
        async def _broken(values):
            raise RuntimeError("db down")

        monkeypatch.setattr(admin_config, "write_app_settings", _broken)
        with pytest.raises(HTTPException) as info:
            await admin_config.select_llm(admin_config.LLMConfigRequest(provider="ollama", model="m"))
        assert info.value.status_code == 503
        assert admin_config.get_llm_override() is None


class TestPersonas:
    async def test_a_custom_persona_and_the_selection_survive_a_restart(self, migrated, monkeypatch):
        await personas.create_persona(CUSTOM)
        await personas.activate_persona("maritime")
        _restart(monkeypatch)
        assert "maritime" not in personas._personas

        await admin_config.refresh_persisted_settings()

        assert personas._personas["maritime"]["description"] == "Shipping and ports"
        assert personas._active_persona == "maritime"
        assert personas._personas["maritime"]["active"] is True
        assert personas.active_persona()["name"] == "Maritime Analyst"
        assert sum(p["active"] for p in personas._personas.values()) == 1

    async def test_activating_a_builtin_survives_a_restart(self, migrated, monkeypatch):
        await personas.activate_persona("cyber_analyst")
        _restart(monkeypatch)
        await admin_config.refresh_persisted_settings()
        assert personas._active_persona == "cyber_analyst"

    async def test_a_deletion_survives_a_restart(self, migrated, monkeypatch):
        await personas.create_persona(CUSTOM)
        await personas.delete_persona("maritime")
        _restart(monkeypatch)
        await admin_config.refresh_persisted_settings()
        assert "maritime" not in personas._personas

    async def test_a_row_cannot_overwrite_a_builtin(self, migrated, monkeypatch):
        original = copy.deepcopy(personas._BUILTIN_PERSONAS["allsource"])
        tampered = {"allsource": {"id": "allsource", "name": "Hijacked", "description": "x", "skills": [], "temperature": 1.0}}
        await admin_config.write_app_settings({personas.CUSTOM_PERSONAS_KEY: json.dumps(tampered)})
        await admin_config.refresh_persisted_settings()
        assert personas._personas["allsource"]["name"] == original["name"]

    async def test_an_active_id_that_no_longer_exists_is_ignored(self, migrated):
        await admin_config.write_app_settings({personas.ACTIVE_PERSONA_KEY: "deleted-long-ago"})
        await admin_config.refresh_persisted_settings()
        assert personas._active_persona == personas._DEFAULT_ACTIVE

    async def test_an_unreadable_row_keeps_the_builtins(self, migrated):
        await admin_config.write_app_settings({personas.CUSTOM_PERSONAS_KEY: "{not json"})
        await admin_config.refresh_persisted_settings()
        assert set(personas._BUILTIN_PERSONA_IDS) <= set(personas._personas)

    async def test_a_failed_save_changes_nothing(self, migrated, monkeypatch):
        async def _broken(values):
            raise RuntimeError("db down")

        monkeypatch.setattr(admin_config, "write_app_settings", _broken)
        with pytest.raises(HTTPException) as info:
            await personas.create_persona(CUSTOM)
        assert info.value.status_code == 503
        assert "maritime" not in personas._personas
        with pytest.raises(HTTPException):
            await personas.activate_persona("cyber_analyst")
        assert personas._active_persona == personas._DEFAULT_ACTIVE

    async def test_a_builtin_id_is_still_refused(self, migrated):
        with pytest.raises(HTTPException) as info:
            await personas.create_persona(personas.PersonaRequest(
                id="allsource", name="x", description="x", skills=[],
            ))
        assert info.value.status_code == 409
        assert await _row(migrated, personas.CUSTOM_PERSONAS_KEY) is None
