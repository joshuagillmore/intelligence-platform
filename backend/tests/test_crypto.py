"""Secrets at rest: a value that cannot be decrypted is unreadable, not a key.

On InvalidToken (a wrong or rotated ENCRYPTION_KEY), `decrypt` returned the
ciphertext itself, which was then sent to the provider as the API key. Without
ENCRYPTION_KEY, keys were stored in plaintext while SECURITY.md promised Fernet
at rest, and REQUIRE_SECURE_AUTH did not notice.
"""
from __future__ import annotations

import types

import pytest
from cryptography.fernet import Fernet

from intel_platform import crypto

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


def _use_key(monkeypatch, key: str):
    monkeypatch.setattr("intel_platform.config.settings", types.SimpleNamespace(encryption_key=key))


class TestDecrypt:
    def test_round_trip(self, monkeypatch):
        _use_key(monkeypatch, KEY_A)
        token = crypto.encrypt("sk-live-123")
        assert token != "sk-live-123"
        assert crypto.decrypt(token) == "sk-live-123"

    def test_a_token_from_another_key_is_unreadable_not_returned(self, monkeypatch):
        _use_key(monkeypatch, KEY_A)
        token = crypto.encrypt("sk-live-123")
        _use_key(monkeypatch, KEY_B)
        assert crypto.decrypt(token) is None

    def test_plaintext_stored_before_encryption_is_unreadable_once_a_key_is_set(self, monkeypatch):
        _use_key(monkeypatch, KEY_A)
        assert crypto.decrypt("sk-live-123") is None

    def test_without_a_key_plaintext_reads_back(self, monkeypatch):
        _use_key(monkeypatch, "")
        assert crypto.encrypt("sk-live-123") == "sk-live-123"
        assert crypto.decrypt("sk-live-123") == "sk-live-123"

    def test_without_a_key_a_stored_token_is_not_returned_as_the_key(self, monkeypatch):
        """The same failure from the other side: the key was removed after encrypting."""
        _use_key(monkeypatch, KEY_A)
        token = crypto.encrypt("sk-live-123")
        _use_key(monkeypatch, "")
        assert crypto.decrypt(token) is None


class TestEncryptionProblem:
    def test_blank_is_a_problem(self):
        assert crypto.encryption_problem("")

    def test_an_invalid_key_is_a_problem(self):
        assert crypto.encryption_problem("not-a-fernet-key")

    def test_a_valid_key_is_fine(self):
        assert crypto.encryption_problem(KEY_A) is None


class TestSecureAuthRequiresEncryption:
    def _settings(self, **overrides):
        base = dict(
            jwt_secret="j" * 32, api_key="k" * 16, default_admin_password="x" * 12,
            require_secure_auth=True, encryption_key=KEY_A, mcp_enabled=False,
        )
        base.update(overrides)
        return types.SimpleNamespace(**base)

    @pytest.mark.parametrize("key", ["", "not-a-fernet-key"])
    def test_boot_is_refused_without_a_usable_key(self, monkeypatch, key):
        from intel_platform.api import app as app_module

        monkeypatch.setattr(app_module, "settings", self._settings(encryption_key=key))
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
            app_module._enforce_secure_auth()

    def test_boot_warns_without_a_key_even_when_not_enforced(self, monkeypatch):
        from intel_platform.api import app as app_module

        monkeypatch.setattr(app_module, "settings", self._settings(require_secure_auth=False, encryption_key=""))
        assert any("ENCRYPTION_KEY" in p for p in app_module._insecure_defaults())


class TestStoredKeysThatCannotBeRead:
    def test_the_admin_list_marks_them_instead_of_failing(self):
        from intel_platform.api.routes.admin_config import _mask_key

        assert _mask_key(None) == "(unreadable)"

    async def test_an_unreadable_active_key_is_no_key(self, monkeypatch):
        """None lets provider resolution fall back to the environment key,
        instead of sending a Fernet token to the provider as the API key."""
        from intel_platform.api.routes import admin_config

        _use_key(monkeypatch, KEY_A)
        stored = Fernet(KEY_B.encode()).encrypt(b"sk-live-123").decode()

        class _Result:
            def scalar_one_or_none(self):
                return stored

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement):
                return _Result()

        monkeypatch.setattr(admin_config, "get_session_factory", lambda: (lambda: _Session()))
        assert await admin_config.get_active_api_key("anthropic") is None
