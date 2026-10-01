"""Cookie sessions (contract 8; review focus 4).

The UI kept its JWT in localStorage, where any script that runs in the page —
an XSS in rendered document text — can read it. Login now sets an httpOnly
`sentinel_session` cookie and no longer returns the token. A cookie is sent by
the browser on its own, though, so a cookie-authenticated request that changes
state must also carry `X-Requested-With: sentinel`, which a cross-site form
cannot set: without it, 403. Bearer tokens and the API key are unaffected.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from intel_platform.api import auth as auth_module
from intel_platform.api.app import app
from intel_platform.api.deps import get_graph_store
from intel_platform.api.routes import auth as auth_routes
from intel_platform.config import get_settings, settings

HEADER = {"X-Requested-With": "sentinel"}


@pytest.fixture
def client():
    with_app = TestClient(app)
    yield with_app
    with_app.close()


@pytest.fixture
def known_user(monkeypatch):
    """Login without Neo4j: one analyst whose password is 'correct-horse-1'."""
    def _authenticate(username, password):
        if username == "analyst-c" and password == "correct-horse-1":
            return {"username": "analyst-c", "role": "analyst"}
        return None

    monkeypatch.setattr(auth_routes, "authenticate_user", _authenticate)
    auth_module._failed_logins.clear()
    yield "analyst-c"
    auth_module._failed_logins.clear()


@pytest.fixture
def empty_store():
    """DELETE /api/reports/{id} with nothing stored: 404 once past auth."""
    class _Store:
        def get_entity(self, _id):
            return None

    app.dependency_overrides[get_graph_store] = lambda: _Store()
    yield
    app.dependency_overrides.pop(get_graph_store, None)


def _login(client, password="correct-horse-1"):
    return client.post("/api/auth/login", json={"username": "analyst-c", "password": password})


def _set_cookie_header(resp) -> str:
    (header,) = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    return header


class TestLogin:
    def test_sets_an_httponly_lax_session_cookie(self, client, known_user):
        resp = _login(client)
        assert resp.status_code == 200
        header = _set_cookie_header(resp)
        assert header.startswith(f"{settings.session_cookie_name}=")
        lowered = header.lower()
        assert "httponly" in lowered
        assert "samesite=lax" in lowered
        assert "path=/" in lowered
        assert f"max-age={settings.session_cookie_max_age}" in lowered
        assert "secure" not in lowered.replace("samesite", ""), "Secure only when configured"

    def test_secure_when_configured(self, client, known_user, monkeypatch):
        monkeypatch.setattr(get_settings(), "session_cookie_secure", True)
        assert "; secure" in _set_cookie_header(_login(client)).lower()

    def test_the_body_no_longer_carries_the_token(self, client, known_user):
        body = _login(client).json()
        assert "access_token" not in body
        assert (body["username"], body["role"]) == ("analyst-c", "analyst")

    def test_the_cookie_is_a_token_for_that_user_lasting_the_session(self, client, known_user):
        import jwt

        _login(client)
        claims = jwt.decode(client.cookies[settings.session_cookie_name], settings.jwt_secret, algorithms=["HS256"])
        assert (claims["sub"], claims["role"]) == ("analyst-c", "analyst")
        # The token lasts as long as the cookie, so neither outlives the other.
        assert claims["exp"] - claims.get("iat", claims["exp"] - settings.session_cookie_max_age) == settings.session_cookie_max_age

    def test_a_failed_login_sets_nothing(self, client, known_user):
        resp = _login(client, password="wrong")
        assert resp.status_code == 401
        assert "set-cookie" not in {k.lower() for k in resp.headers}


class TestCookieAuthentication:
    def test_me_identifies_the_cookie_holder(self, client, known_user):
        _login(client)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json() == {"username": "analyst-c", "role": "analyst"}

    def test_reads_need_no_header(self, client, known_user):
        _login(client)
        assert client.get("/api/personas").status_code == 200

    def test_a_state_changing_request_without_the_header_is_403(self, client, known_user, empty_store):
        """Review focus 4: a cross-site form post cannot act as the analyst."""
        _login(client)
        resp = client.delete("/api/reports/nothing-here")
        assert resp.status_code == 403
        assert "X-Requested-With" in resp.json()["detail"]

    def test_a_form_post_shaped_request_is_403(self, client, known_user):
        _login(client)
        resp = client.post(
            "/api/auth/change-password",
            data={"current_password": "correct-horse-1", "new_password": "attacker-chosen-1"},
        )
        assert resp.status_code == 403

    def test_with_the_header_it_goes_through(self, client, known_user, empty_store):
        _login(client)
        assert client.delete("/api/reports/nothing-here", headers=HEADER).status_code == 404

    def test_a_wrong_header_value_is_403(self, client, known_user, empty_store):
        _login(client)
        resp = client.delete("/api/reports/nothing-here", headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 403

    @pytest.mark.parametrize("method", ["get", "head", "options"])
    def test_safe_methods_need_no_header(self, client, known_user, method):
        _login(client)
        resp = getattr(client, method)("/api/auth/me")
        assert resp.status_code != 403

    def test_an_invalid_cookie_is_401(self, client):
        client.cookies.set(settings.session_cookie_name, "not-a-jwt")
        assert client.get("/api/auth/me").status_code == 401

    def test_an_expired_cookie_is_401(self, client):
        token = auth_module.create_access_token("analyst-c", "analyst", expires_in=timedelta(seconds=-1))
        client.cookies.set(settings.session_cookie_name, token)
        assert client.get("/api/auth/me").status_code == 401

    def test_the_api_key_in_a_cookie_does_not_authenticate(self, client):
        """The API key is a header credential; a cookie carrying it is nothing."""
        client.cookies.set(settings.session_cookie_name, settings.api_key)
        assert client.get("/api/auth/me").status_code == 401

    def test_no_credentials_is_401(self, client):
        assert client.get("/api/auth/me").status_code == 401


class TestOtherCallersAreUnaffected:
    def test_a_bearer_token_needs_no_header(self, client, empty_store):
        token = auth_module.create_access_token("analyst-b", "analyst")
        resp = client.delete("/api/reports/nothing-here", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_the_api_key_needs_no_header(self, client, empty_store):
        resp = client.delete("/api/reports/nothing-here", headers={"Authorization": f"Bearer {settings.api_key}"})
        assert resp.status_code == 404

    def test_me_with_a_bearer_token(self, client):
        token = auth_module.create_access_token("analyst-b", "analyst")
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.json() == {"username": "analyst-b", "role": "analyst"}

    def test_a_bearer_token_wins_over_a_cookie(self, client):
        client.cookies.set(settings.session_cookie_name, auth_module.create_access_token("cookie-user", "admin"))
        token = auth_module.create_access_token("bearer-user", "analyst")
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["username"] == "bearer-user"

    def test_direct_callers_still_pass_credentials_positionally(self):
        """The MCP transport calls get_current_user with credentials alone."""
        from fastapi.security import HTTPAuthorizationCredentials

        token = auth_module.create_access_token("analyst-m", "analyst")
        user = auth_module.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
        assert user["username"] == "analyst-m"


class TestLogout:
    def test_clears_the_cookie(self, client, known_user):
        _login(client)
        resp = client.post("/api/auth/logout", headers=HEADER)
        assert resp.status_code == 200
        header = _set_cookie_header(resp).lower()
        assert header.startswith(f"{settings.session_cookie_name}=")
        assert "max-age=0" in header
        assert settings.session_cookie_name not in client.cookies
        assert client.get("/api/auth/me").status_code == 401

    def test_needs_the_header(self, client, known_user):
        """A cross-site form must not be able to sign the analyst out."""
        _login(client)
        assert client.post("/api/auth/logout").status_code == 403
        assert client.get("/api/auth/me").status_code == 200

    def test_works_without_a_live_session(self, client):
        assert client.post("/api/auth/logout", headers=HEADER).status_code == 200
