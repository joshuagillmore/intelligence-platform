"""The auth paths the suite never exercised (I-12).

Nothing tested the admin/admin seed refusal under REQUIRE_SECURE_AUTH, the
login endpoint itself, or the lockout; and a Neo4j that goes away mid-request
must produce a clean 503, not a 500 carrying driver detail or a hang.
"""
from __future__ import annotations

import types

import jwt
import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from intel_platform.api import auth as auth_module
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
PREFIX = "test-i12-"


# ---------------------------------------------------------------------------
# Seeding the first admin
# ---------------------------------------------------------------------------

class _SeedSession:
    """A database with no users: records what the seed path writes."""

    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.log.append((query, params))
        if "count(u)" in query:
            return types.SimpleNamespace(single=lambda: {"cnt": 0})
        return []


@pytest.fixture
def empty_db(monkeypatch):
    log: list = []
    monkeypatch.setattr(auth_module, "_get_driver", lambda: types.SimpleNamespace(session=lambda: _SeedSession(log)))
    return log


def _settings(**overrides):
    base = dict(require_secure_auth=True, default_admin_password="")
    base.update(overrides)
    return types.SimpleNamespace(**base)


class TestSeed:
    @pytest.mark.parametrize("password", ["", "admin"])
    def test_secure_auth_refuses_to_seed_admin_admin(self, empty_db, monkeypatch, password):
        monkeypatch.setattr("intel_platform.config.settings", _settings(default_admin_password=password))
        with pytest.raises(RuntimeError, match="DEFAULT_ADMIN_PASSWORD"):
            auth_module._ensure_default_admin()
        assert not [q for q, _ in empty_db if "CREATE" in q]

    def test_the_configured_password_is_what_gets_seeded(self, empty_db, monkeypatch):
        monkeypatch.setattr("intel_platform.config.settings", _settings(default_admin_password="seeded-pw-1"))
        auth_module._ensure_default_admin()
        (created,) = [p for q, p in empty_db if "CREATE" in q]
        assert created["username"] == "admin" and created["role"] == "admin"
        assert auth_module.verify_password("seeded-pw-1", created["hashed_password"])
        assert not auth_module.verify_password("admin", created["hashed_password"])


# ---------------------------------------------------------------------------
# /api/auth/login and the lockout, over HTTP
# ---------------------------------------------------------------------------

@pytest.fixture
def user(neo4j_driver):
    username = PREFIX + "analyst"
    with neo4j_driver.session() as session:
        session.run(
            "CREATE (u:User {username: $u, hashed_password: $h, role: 'analyst', created_at: datetime()})",
            u=username, h=auth_module._hash_password("correct-horse-1"),
        )
    auth_module._failed_logins.clear()
    yield username
    with neo4j_driver.session() as session:
        session.run("MATCH (u:User) WHERE u.username STARTS WITH $p DETACH DELETE u", p=PREFIX)
    auth_module._failed_logins.clear()


def _login(username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestLogin:
    def test_a_correct_password_returns_a_token_for_that_user(self, user):
        resp = _login(user, "correct-horse-1")
        assert resp.status_code == 200
        body = resp.json()
        claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
        assert (claims["sub"], claims["role"]) == (user, "analyst")
        assert (body["username"], body["role"]) == (user, "analyst")

    def test_the_token_authenticates_api_calls(self, user):
        token = _login(user, "correct-horse-1").json()["access_token"]
        resp = client.get("/api/personas", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_wrong_password_and_unknown_user_are_indistinguishable(self, user):
        wrong = _login(user, "wrong-password")
        unknown = _login(PREFIX + "nobody", "wrong-password")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_five_failures_lock_the_account_even_for_the_right_password(self, user):
        for _ in range(auth_module.MAX_LOGIN_ATTEMPTS):
            assert _login(user, "wrong-password").status_code == 401
        assert _login(user, "correct-horse-1").status_code == 429

    def test_one_accounts_lockout_does_not_lock_out_another(self, user, neo4j_driver):
        other = PREFIX + "other"
        with neo4j_driver.session() as session:
            session.run(
                "CREATE (u:User {username: $u, hashed_password: $h, role: 'analyst'})",
                u=other, h=auth_module._hash_password("other-pass-1"),
            )
        for _ in range(auth_module.MAX_LOGIN_ATTEMPTS):
            _login(user, "wrong-password")
        assert _login(other, "other-pass-1").status_code == 200

    def test_a_success_resets_the_accounts_count(self, user):
        for _ in range(auth_module.MAX_LOGIN_ATTEMPTS - 1):
            _login(user, "wrong-password")
        assert _login(user, "correct-horse-1").status_code == 200
        for _ in range(auth_module.MAX_LOGIN_ATTEMPTS - 1):
            _login(user, "wrong-password")
        assert _login(user, "correct-horse-1").status_code == 200


# ---------------------------------------------------------------------------
# Neo4j unreachable (plan review focus 2)
# ---------------------------------------------------------------------------

@pytest.fixture
def dead_neo4j():
    driver = GraphDatabase.driver("bolt://127.0.0.1:1", auth=("neo4j", "x"), connection_timeout=1)
    yield driver
    driver.close()


class TestDeadDatabase:
    def test_health_answers_degraded_without_hanging(self, dead_neo4j, monkeypatch):
        from intel_platform.api.routes import health

        monkeypatch.setattr(health, "get_neo4j_driver", lambda: dead_neo4j)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["neo4j_connected"] is False
        assert resp.json()["status"] == "degraded"

    @pytest.mark.parametrize("call", [
        lambda: client.post("/api/ingest", data={"project_id": PREFIX + "p", "content": "Kolvane met Marek."},
                            headers={"Authorization": f"Bearer {settings.api_key}"}),
        lambda: client.get("/api/graph", params={"project_id": PREFIX + "p"},
                           headers={"Authorization": f"Bearer {settings.api_key}"}),
        lambda: client.get("/api/documents", params={"project_id": PREFIX + "p"},
                           headers={"Authorization": f"Bearer {settings.api_key}"}),
    ], ids=["ingest (to_thread)", "graph (sync route)", "documents (sync route)"])
    def test_routes_answer_503_without_driver_detail(self, dead_neo4j, call):
        from intel_platform.api.deps import get_graph_store
        from intel_platform.graph.store import GraphStore

        app.dependency_overrides[get_graph_store] = lambda: GraphStore(dead_neo4j)
        try:
            resp = call()
        finally:
            app.dependency_overrides.pop(get_graph_store, None)
        assert resp.status_code == 503
        assert "127.0.0.1" not in resp.text and "bolt" not in resp.text.lower()

    def test_login_answers_503_when_the_user_store_is_down(self, dead_neo4j, monkeypatch):
        monkeypatch.setattr(auth_module, "_get_driver", lambda: dead_neo4j)
        auth_module._failed_logins.clear()
        resp = _login(PREFIX + "anyone", "whatever-1")
        assert resp.status_code == 503
        assert auth_module._failed_logins == {}, "an outage is not a failed guess"
