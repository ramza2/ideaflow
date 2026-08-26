"""Unit tests for auth security helpers (no database)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    sha256_hex,
    verify_password,
)
from app.schemas.auth import PasswordChangeRequest
from app.services.auth import validate_preauth_csrf


def test_password_hash_roundtrip() -> None:
    password = "correct-horse-battery"
    digest = hash_password(password)
    assert digest != password
    assert verify_password(password, digest)
    assert not verify_password("wrong-password", digest)


def test_session_token_hashing() -> None:
    raw = generate_session_token()
    assert len(raw) >= 32
    h1 = sha256_hex(raw)
    h2 = sha256_hex(raw)
    assert h1 == h2
    assert h1 != raw
    assert len(h1) == 64


def test_csrf_token_hashing() -> None:
    raw = generate_csrf_token()
    assert sha256_hex(raw) != raw
    assert len(sha256_hex(raw)) == 64


def test_preauth_csrf_compare_digest_accepts_match() -> None:
    token = generate_csrf_token()
    validate_preauth_csrf(token, token)


def test_preauth_csrf_compare_digest_rejects_mismatch() -> None:
    with pytest.raises(AppError) as exc:
        validate_preauth_csrf(generate_csrf_token(), generate_csrf_token())
    assert exc.value.code == "CSRF_INVALID"


def test_cookie_samesite_normalized() -> None:
    assert Settings(AUTH_COOKIE_SAMESITE="LAX").auth_cookie_samesite == "lax"
    assert Settings(AUTH_COOKIE_SAMESITE="bogus").auth_cookie_samesite == "lax"
    assert Settings(AUTH_COOKIE_SAMESITE="strict").auth_cookie_samesite == "strict"


def test_password_schema_min_length() -> None:
    with pytest.raises(ValidationError):
        PasswordChangeRequest(current_password="old-password-1", new_password="short")


def test_password_schema_rejects_same() -> None:
    with pytest.raises(ValidationError):
        PasswordChangeRequest(
            current_password="same-password-ok",
            new_password="same-password-ok",
        )


def test_password_schema_accepts_valid() -> None:
    req = PasswordChangeRequest(
        current_password="old-password-1",
        new_password="new-password-ok",
    )
    assert req.new_password == "new-password-ok"
