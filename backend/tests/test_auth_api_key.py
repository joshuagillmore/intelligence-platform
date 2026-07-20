"""P0 auth-safety guards.

The built-in default API key ships in .env.example, so it must NEVER authenticate
(it previously minted an admin identity for any request that echoed it). A strong,
non-default API key must still work, because it is the legacy bearer token for
programmatic / service-to-service callers (the browser frontend authenticates with
a JWT, not this key). Boot must also warn loudly whenever a default secret remains.
"""
import types

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from intel_platform.api import auth as auth_module


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_default_api_key_does_not_authenticate(monkeypatch):
    """The placeholder key from .env.example must NOT grant admin (or any) access."""
    fake = types.SimpleNamespace(api_key=auth_module._DEFAULT_API_KEY)
    monkeypatch.setattr("intel_platform.config.settings", fake)

    with pytest.raises(HTTPException) as exc:
        auth_module.get_current_user(_creds(auth_module._DEFAULT_API_KEY))
    assert exc.value.status_code == 401


def test_blank_api_key_does_not_authenticate(monkeypatch):
    """An unset API key must not let an empty/blank bearer token through either."""
    fake = types.SimpleNamespace(api_key="")
    monkeypatch.setattr("intel_platform.config.settings", fake)

    with pytest.raises(HTTPException) as exc:
        auth_module.get_current_user(_creds(""))
    assert exc.value.status_code == 401


def test_non_default_api_key_authenticates_as_admin(monkeypatch):
    """A strong, non-default API key still authenticates (frontend relies on it)."""
    fake = types.SimpleNamespace(api_key="a-strong-unique-key")
    monkeypatch.setattr("intel_platform.config.settings", fake)

    user = auth_module.get_current_user(_creds("a-strong-unique-key"))
    assert user == {"username": "api_key_user", "role": "admin"}


def test_valid_jwt_still_authenticates_when_api_key_path_disabled(monkeypatch):
    """A JWT minted by the app authenticates even when the API-key path is disabled."""
    fake = types.SimpleNamespace(api_key=auth_module._DEFAULT_API_KEY)
    monkeypatch.setattr("intel_platform.config.settings", fake)

    token = auth_module.create_access_token("analyst-1", role="analyst")
    user = auth_module.get_current_user(_creds(token))
    assert user == {"username": "analyst-1", "role": "analyst"}


def test_boot_warns_on_default_secrets(monkeypatch, caplog):
    """A loud WARNING must fire at boot for each default secret still in place."""
    from intel_platform.api import app as app_module

    fake = types.SimpleNamespace(
        api_key=auth_module._DEFAULT_API_KEY,
        default_admin_password="",
        require_secure_auth=False,
    )
    monkeypatch.setattr(app_module, "settings", fake)

    problems = app_module._insecure_defaults()
    assert any("API_KEY" in p for p in problems)
    assert any("DEFAULT_ADMIN_PASSWORD" in p for p in problems)

    with caplog.at_level("WARNING"):
        app_module._warn_insecure_defaults()
    assert "insecure default" in caplog.text.lower()


def test_register_request_invalid_input_raises_validation_error():
    """Invalid RegisterRequest must raise a Pydantic ValidationError (FastAPI ->
    422), not a bare ValueError from model_post_init (which escaped as 500)."""
    from pydantic import ValidationError

    from intel_platform.api.routes.auth import RegisterRequest

    with pytest.raises(ValidationError):
        RegisterRequest(username="ab", password="longenough")  # username too short
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="short")  # password too short
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="longenough", role="root")  # bad role


def test_register_request_accepts_valid_input():
    from intel_platform.api.routes.auth import RegisterRequest

    req = RegisterRequest(username="alice", password="longenough", role="admin")
    assert req.username == "alice"
    assert req.role == "admin"
