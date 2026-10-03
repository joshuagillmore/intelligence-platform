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

_JWT = "test-jwt-secret-of-at-least-32-bytes"


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_default_api_key_does_not_authenticate(monkeypatch):
    """The placeholder key from .env.example must NOT grant admin (or any) access."""
    fake = types.SimpleNamespace(api_key=auth_module._DEFAULT_API_KEY, jwt_secret=_JWT)
    monkeypatch.setattr("intel_platform.config.settings", fake)

    with pytest.raises(HTTPException) as exc:
        auth_module.get_current_user(_creds(auth_module._DEFAULT_API_KEY))
    assert exc.value.status_code == 401


def test_blank_api_key_does_not_authenticate(monkeypatch):
    """An unset API key must not let an empty/blank bearer token through either."""
    fake = types.SimpleNamespace(api_key="", jwt_secret=_JWT)
    monkeypatch.setattr("intel_platform.config.settings", fake)

    with pytest.raises(HTTPException) as exc:
        auth_module.get_current_user(_creds(""))
    assert exc.value.status_code == 401


def test_non_default_api_key_authenticates_as_admin(monkeypatch):
    """A strong, non-default API key still authenticates (frontend relies on it)."""
    fake = types.SimpleNamespace(api_key="a-strong-unique-key", jwt_secret=_JWT)
    monkeypatch.setattr("intel_platform.config.settings", fake)

    user = auth_module.get_current_user(_creds("a-strong-unique-key"))
    assert user == {"username": "api_key_user", "role": "admin"}


def test_valid_jwt_still_authenticates_when_api_key_path_disabled(monkeypatch):
    """A JWT minted by the app authenticates even when the API-key path is disabled."""
    fake = types.SimpleNamespace(api_key=auth_module._DEFAULT_API_KEY, jwt_secret=_JWT)
    monkeypatch.setattr("intel_platform.config.settings", fake)

    token = auth_module.create_access_token("analyst-1", role="analyst")
    user = auth_module.get_current_user(_creds(token))
    assert user == {"username": "analyst-1", "role": "analyst"}


def test_boot_warns_on_default_secrets(monkeypatch, caplog):
    """A loud WARNING must fire at boot for each default secret still in place."""
    from intel_platform.api import app as app_module

    fake = types.SimpleNamespace(
        api_key=auth_module._DEFAULT_API_KEY,
        jwt_secret=_JWT,
        encryption_key="",
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


def test_the_api_key_is_compared_in_constant_time(monkeypatch):
    """Low -> A: `==` returns at the first differing byte, leaking the key's
    prefix through response timing."""
    import hmac

    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(auth_module.hmac, "compare_digest", spy)
    monkeypatch.setattr(
        "intel_platform.config.settings",
        types.SimpleNamespace(api_key="a-strong-unique-key", jwt_secret=_JWT),
    )
    assert auth_module.get_current_user(_creds("a-strong-unique-key"))["role"] == "admin"
    assert calls, "the API key was not compared with hmac.compare_digest"


def test_an_unknown_user_costs_a_password_check_too(monkeypatch):
    """Low -> A: login returned before bcrypt for an unknown username, so its
    speed told an attacker which usernames exist."""
    checked = []
    monkeypatch.setattr(auth_module, "verify_password", lambda plain, hashed: checked.append(hashed) or False)

    class _Empty:
        def single(self):
            return None

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, *a, **kw):
            return _Empty()

    monkeypatch.setattr(auth_module, "_get_driver", lambda: types.SimpleNamespace(session=_Session))
    assert auth_module.authenticate_user("no-such-user", "guess") is None
    assert len(checked) == 1


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


def test_the_api_key_identity_cannot_be_registered():
    """The API key acts as ``api_key_user`` and owns the projects it creates, so
    a registered account by that name would sign in as their owner."""
    from pydantic import ValidationError

    from intel_platform.api.routes.auth import RegisterRequest

    with pytest.raises(ValidationError, match="reserved"):
        RegisterRequest(username="api_key_user", password="longenough")


def test_register_request_accepts_valid_input():
    from intel_platform.api.routes.auth import RegisterRequest

    req = RegisterRequest(username="alice", password="longenough", role="admin")
    assert req.username == "alice"
    assert req.role == "admin"
