"""REQUIRE_SECURE_AUTH must judge the secrets actually in effect.

It compared JWT_SECRET only against the literal built-in default, so
`JWT_SECRET=` (present but blank) passed — and PyJWT signs and verifies HS256
with an empty key, so anyone could mint an admin token for a deploy that had
declared itself hardened. A short API_KEY passed the same way and authenticates
as admin. The boundaries are tested on both sides: 31 bytes is refused, 32 is
accepted, and length is measured in bytes, not characters.
"""
from __future__ import annotations

import types

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from intel_platform.api import app as app_module
from intel_platform.api import auth as auth_module

STRONG_JWT = "j" * 32
STRONG_API_KEY = "k" * 16
VALID_FERNET_KEY = Fernet.generate_key().decode()


def _settings(**overrides):
    base = dict(
        jwt_secret=STRONG_JWT,
        api_key=STRONG_API_KEY,
        default_admin_password="a-strong-admin-password",
        require_secure_auth=True,
        encryption_key=VALID_FERNET_KEY,
        mcp_enabled=False,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


class TestJwtSecretProblem:
    def test_blank_secret_is_a_problem(self):
        assert auth_module.jwt_secret_problem("")

    def test_builtin_default_is_a_problem(self):
        assert auth_module.jwt_secret_problem(auth_module._DEFAULT_JWT_SECRET)

    def test_31_bytes_is_a_problem(self):
        assert auth_module.jwt_secret_problem("x" * 31)

    def test_32_bytes_is_accepted(self):
        assert auth_module.jwt_secret_problem("x" * 32) is None

    def test_length_is_measured_in_bytes_not_characters(self):
        # 16 two-byte characters are 32 bytes of key material: accepted.
        assert auth_module.jwt_secret_problem("é" * 16) is None
        # 15 two-byte characters plus one ASCII byte is 31 bytes: refused,
        # although it is only 16 characters long.
        assert auth_module.jwt_secret_problem("é" * 15 + "x")


class TestApiKeyProblem:
    def test_blank_key_disables_the_path_and_is_not_a_problem(self):
        assert auth_module.api_key_problem("") is None

    def test_builtin_default_is_a_problem(self):
        assert auth_module.api_key_problem(auth_module._DEFAULT_API_KEY)

    def test_15_bytes_is_a_problem(self):
        assert auth_module.api_key_problem("k" * 15)

    def test_16_bytes_is_accepted(self):
        assert auth_module.api_key_problem("k" * 16) is None


class TestEnforceSecureAuth:
    def test_blank_jwt_secret_refuses_boot(self, monkeypatch):
        monkeypatch.setattr(app_module, "settings", _settings(jwt_secret=""))
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            app_module._enforce_secure_auth()

    def test_31_byte_jwt_secret_refuses_boot(self, monkeypatch):
        monkeypatch.setattr(app_module, "settings", _settings(jwt_secret="x" * 31))
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            app_module._enforce_secure_auth()

    def test_32_byte_jwt_secret_boots(self, monkeypatch):
        monkeypatch.setattr(app_module, "settings", _settings(jwt_secret="x" * 32))
        app_module._enforce_secure_auth()

    def test_short_api_key_refuses_boot(self, monkeypatch):
        monkeypatch.setattr(app_module, "settings", _settings(api_key="k" * 15))
        with pytest.raises(RuntimeError, match="API_KEY"):
            app_module._enforce_secure_auth()

    def test_default_api_key_refuses_boot(self, monkeypatch):
        monkeypatch.setattr(app_module, "settings", _settings(api_key=auth_module._DEFAULT_API_KEY))
        with pytest.raises(RuntimeError, match="API_KEY"):
            app_module._enforce_secure_auth()

    def test_nothing_is_enforced_without_the_flag(self, monkeypatch):
        monkeypatch.setattr(
            app_module, "settings",
            _settings(require_secure_auth=False, jwt_secret="", api_key="short"),
        )
        app_module._enforce_secure_auth()

    def test_boot_warning_names_a_blank_jwt_secret(self, monkeypatch):
        monkeypatch.setattr(
            app_module, "settings", _settings(require_secure_auth=False, jwt_secret=""),
        )
        assert any("JWT_SECRET" in p for p in app_module._insecure_defaults())

    def test_boot_warning_names_a_short_api_key(self, monkeypatch):
        monkeypatch.setattr(
            app_module, "settings", _settings(require_secure_auth=False, api_key="k" * 15),
        )
        assert any("API_KEY" in p for p in app_module._insecure_defaults())


class TestSecretIsReadFromSettings:
    """The secret was read from os.environ once, at import. Reading it from
    Settings is what lets the boot check and the signer agree on one value."""

    def _creds(self, token: str) -> HTTPAuthorizationCredentials:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_token_is_signed_with_the_configured_secret(self, monkeypatch):
        monkeypatch.setattr(
            "intel_platform.config.settings", _settings(jwt_secret="s" * 40, api_key=""),
        )
        token = auth_module.create_access_token("alice", role="analyst")
        assert jwt.decode(token, "s" * 40, algorithms=["HS256"])["sub"] == "alice"

    def test_a_token_signed_with_another_secret_is_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "intel_platform.config.settings", _settings(jwt_secret="s" * 40, api_key=""),
        )
        forged = jwt.encode({"sub": "mallory", "role": "admin"}, "", algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            auth_module.get_current_user(self._creds(forged))
        assert exc.value.status_code == 401
