"""Symmetric encryption for secrets stored at rest (API keys, credentials)."""
from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

_logger = logging.getLogger(__name__)

_ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _ENCRYPTION_KEY:
        _logger.warning("SECURITY: ENCRYPTION_KEY not set — API keys stored in plaintext")
        return None
    try:
        _fernet = Fernet(_ENCRYPTION_KEY.encode())
        return _fernet
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


def decrypt(ciphertext: str) -> str:
    """Decrypt a string. Falls back to returning the input if decryption fails
    (handles migration from plaintext storage)."""
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ciphertext
