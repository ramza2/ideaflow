"""Password hashing, opaque token generation, and SHA-256 digests."""

from __future__ import annotations

import hashlib
import secrets

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()

# Dummy Argon2id hash for timing-safe unknown-email login attempts (not a real password).
DUMMY_PASSWORD_HASH = _password_hash.hash("ideaflow-dummy-password-not-used")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def verify_and_update_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Return (ok, new_hash_or_None). new_hash is set when rehash is recommended."""
    return _password_hash.verify_and_update(password, password_hash)


def generate_session_token() -> str:
    """Cryptographically secure opaque token (~256+ bits)."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
