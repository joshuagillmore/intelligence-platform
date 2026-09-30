"""Activating a stored API key leaves exactly one active key per provider.

The route deactivated keys by the *request's* provider and then activated
`key_id` without looking at it. A mismatched provider left two active keys for
the key's real provider, and `scalar_one_or_none` then raised on every LLM call
that resolved a key for it. Postgres is faked; statements are inspected.
"""
from __future__ import annotations

import types
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from intel_platform.api.app import app
from intel_platform.api.routes import admin_config
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

KEY_ID = uuid.uuid4()


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, stored, log):
        self.stored, self.log = stored, log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement):
        self.log.append(statement)
        if statement.is_select:
            return _Result(self.stored)
        return _Result(None)

    async def commit(self):
        self.log.append("COMMIT")


@pytest.fixture
def db(monkeypatch):
    state = {"stored": types.SimpleNamespace(id=KEY_ID, provider="openai"), "log": []}
    monkeypatch.setattr(admin_config, "get_session_factory", lambda: (lambda: _Session(state["stored"], state["log"])))
    return state


def _updates(log) -> list[str]:
    return [
        str(s.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for s in log if s != "COMMIT" and not s.is_select
    ]


def _activate(key_id, provider):
    return client.put(
        "/api/admin/api-keys/activate", json={"key_id": str(key_id), "provider": provider}, headers=headers,
    )


def test_keys_are_deactivated_for_the_keys_own_provider(db):
    resp = _activate(KEY_ID, "openai")
    assert resp.status_code == 200
    deactivate, activate = _updates(db["log"])
    assert "'openai'" in deactivate and "is_active=false" in deactivate.replace(" ", "")
    assert str(KEY_ID) in activate
    assert db["log"][-1] == "COMMIT"


def test_a_mismatched_provider_is_refused_and_nothing_changes(db):
    resp = _activate(KEY_ID, "anthropic")
    assert resp.status_code == 400
    assert _updates(db["log"]) == []


def test_an_unknown_key_is_404_and_nothing_changes(db):
    db["stored"] = None
    resp = _activate(uuid.uuid4(), "openai")
    assert resp.status_code == 404
    assert _updates(db["log"]) == []


def test_a_malformed_key_id_is_404_not_a_database_error(db):
    resp = _activate("not-a-uuid", "openai")
    assert resp.status_code == 404
    assert db["log"] == []
