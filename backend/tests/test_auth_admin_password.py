"""The admin password is judged by the stored hash, not by the setting.

The check ran only when no users existed, so a deploy that once booted with
admin/admin kept that account forever — REQUIRE_SECURE_AUTH=true included —
and the boot warning read DEFAULT_ADMIN_PASSWORD rather than the database. There
was also no way to change a password at all.

These tests create their own `test-a2-*` users and never pass any other username
to code that writes, so running them against a database that holds a real admin
account cannot change that account.
"""
from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient

from intel_platform.api import auth as auth_module
from intel_platform.api.app import app

client = TestClient(app)
PREFIX = "test-a2-"


def _settings(**overrides):
    base = dict(require_secure_auth=True, default_admin_password="")
    base.update(overrides)
    return types.SimpleNamespace(**base)


@pytest.fixture
def users(neo4j_driver):
    """Create User nodes; delete every `test-a2-*` user afterwards."""
    created: list[str] = []

    def make(name: str, password: str, role: str = "admin") -> str:
        username = PREFIX + name
        with neo4j_driver.session() as session:
            session.run(
                "CREATE (u:User {username: $u, hashed_password: $h, role: $r, created_at: datetime()})",
                u=username, h=auth_module._hash_password(password), r=role,
            )
        created.append(username)
        return username

    yield make
    with neo4j_driver.session() as session:
        session.run("MATCH (u:User) WHERE u.username STARTS WITH $p DETACH DELETE u", p=PREFIX)
    auth_module._failed_logins.clear()


def _stored_password_is(neo4j_driver, username: str, password: str) -> bool:
    with neo4j_driver.session() as session:
        h = session.run(
            "MATCH (u:User {username: $u}) RETURN u.hashed_password AS h", u=username,
        ).single()["h"]
    return auth_module.verify_password(password, h)


class TestStoredHashIsChecked:
    def test_an_admin_still_on_admin_is_found(self, users):
        weak = users("weak", "admin")
        strong = users("strong", "a-real-password")
        found = auth_module._admins_with_default_password()
        assert weak in found
        assert strong not in found

    def test_an_analyst_on_admin_is_not_an_admin_finding(self, users):
        analyst = users("analyst", "admin", role="analyst")
        assert analyst not in auth_module._admins_with_default_password()

    def test_secure_auth_refuses_boot_when_no_replacement_is_configured(self, users, monkeypatch):
        weak = users("refuse", "admin")
        monkeypatch.setattr("intel_platform.config.settings", _settings())
        with pytest.raises(RuntimeError, match="default password"):
            auth_module._enforce_stored_admin_password([weak])

    def test_secure_auth_replaces_it_with_the_configured_password(self, users, monkeypatch, neo4j_driver):
        weak = users("rotate", "admin")
        monkeypatch.setattr(
            "intel_platform.config.settings", _settings(default_admin_password="replacement-pw-1"),
        )
        auth_module._enforce_stored_admin_password([weak])
        assert _stored_password_is(neo4j_driver, weak, "replacement-pw-1")
        assert not _stored_password_is(neo4j_driver, weak, "admin")

    def test_a_configured_password_of_admin_is_not_a_replacement(self, users, monkeypatch):
        weak = users("noop", "admin")
        monkeypatch.setattr(
            "intel_platform.config.settings", _settings(default_admin_password="admin"),
        )
        with pytest.raises(RuntimeError):
            auth_module._enforce_stored_admin_password([weak])

    def test_without_secure_auth_it_warns_and_changes_nothing(self, users, monkeypatch, caplog, neo4j_driver):
        weak = users("warn", "admin")
        monkeypatch.setattr(
            "intel_platform.config.settings",
            _settings(require_secure_auth=False, default_admin_password="replacement-pw-1"),
        )
        with caplog.at_level("WARNING"):
            auth_module._enforce_stored_admin_password([weak])
        assert weak in caplog.text
        assert _stored_password_is(neo4j_driver, weak, "admin")

    def test_boot_consults_the_stored_hashes_even_when_users_exist(self, users, monkeypatch):
        """The old code returned early whenever any user existed."""
        weak = users("boot", "admin")
        monkeypatch.setattr(auth_module, "_admins_with_default_password", lambda: [weak])
        monkeypatch.setattr("intel_platform.config.settings", _settings())
        with pytest.raises(RuntimeError, match="default password"):
            auth_module._ensure_default_admin()


class TestChangePassword:
    def _headers(self, username: str, role: str = "admin") -> dict:
        return {"Authorization": f"Bearer {auth_module.create_access_token(username, role)}"}

    def test_changes_the_password(self, users, neo4j_driver):
        name = users("cp", "old-password-1")
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": "old-password-1", "new_password": "new-password-2"},
            headers=self._headers(name),
        )
        assert resp.status_code == 200
        assert _stored_password_is(neo4j_driver, name, "new-password-2")

    def test_wrong_current_password_is_refused_without_logging_the_user_out(self, users, neo4j_driver):
        name = users("cp-wrong", "old-password-1")
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": "not-it", "new_password": "new-password-2"},
            headers=self._headers(name),
        )
        # 403, not 401: the frontend treats 401 as "session expired" and signs out.
        assert resp.status_code == 403
        assert _stored_password_is(neo4j_driver, name, "old-password-1")

    @pytest.mark.parametrize("new", ["short", "admin"])
    def test_weak_new_passwords_are_rejected(self, users, new):
        name = users(f"cp-weak-{new}", "old-password-1")
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": "old-password-1", "new_password": new},
            headers=self._headers(name),
        )
        assert resp.status_code == 422

    def test_requires_authentication(self):
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": "x" * 8, "new_password": "y" * 8},
        )
        assert resp.status_code == 401

    def test_the_api_key_identity_has_no_password_to_change(self):
        from intel_platform.config import settings
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": "x" * 8, "new_password": "y" * 8},
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        assert resp.status_code == 400
