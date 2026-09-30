"""Symmetric encryption for secrets stored at rest (API keys, credentials)."""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

_logger = logging.getLogger(__name__)

# Fernet tokens start with the version byte 0x80, which url-safe base64 renders
# as "gAAAAA". No provider API key looks like that.
_FERNET_TOKEN_PREFIX = "gAAAAA"

_fernet: tuple[str, Fernet] | None = None


def _configured_key() -> str:
    from intel_platform.config import settings
    return settings.encryption_key or ""


def encryption_problem(key: str) -> str | None:
    """Why this ENCRYPTION_KEY cannot protect secrets at rest, or None when it can."""
    if not key:
        return "ENCRYPTION_KEY is not set (stored API keys would be kept in plaintext)"
    try:
        Fernet(key.encode())
    except Exception:
        return "ENCRYPTION_KEY is not a valid Fernet key (generate one with Fernet.generate_key())"
    return None


def _get_fernet() -> Fernet | None:
    global _fernet
    key = _configured_key()
    if _fernet is not None and _fernet[0] == key:
        return _fernet[1]
    if not key:
        _logger.warning("SECURITY: ENCRYPTION_KEY not set — API keys stored in plaintext")
        return None
    try:
        _fernet = (key, Fernet(key.encode()))
        return _fernet[1]
    except Exception:
        _logger.error("SECURITY: Invalid ENCRYPTION_KEY — must be a valid Fernet key (use Fernet.generate_key())")
        return None


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns the ciphertext as a URL-safe base64 string.
    Falls back to plaintext if no encryption key is configured."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """Decrypt a stored secret. None when it cannot be read.

    A value that cannot be decrypted is unreadable, not a key: returning the
    ciphertext as before sent a Fernet token to the provider as the API key
    whenever ENCRYPTION_KEY was wrong, rotated or removed. Callers treat None
    as "no stored key" and fall back to the environment, and the operator
    re-enters the key under the current ENCRYPTION_KEY.
    """
    f = _get_fernet()
    if f is None:
        if ciphertext.startswith(_FERNET_TOKEN_PREFIX):
            _logger.warning(
                "SECURITY: a stored secret is encrypted but ENCRYPTION_KEY is not set — treating it as unreadable."
            )
            return None
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        _logger.warning(
            "SECURITY: a stored secret could not be decrypted (ENCRYPTION_KEY is wrong or was rotated, "
            "or the value predates encryption) — treating it as unreadable; re-enter it."
        )
        return None
