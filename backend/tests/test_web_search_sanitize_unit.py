"""Unit tests for search query sanitization."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.web_search.sanitize import validate_and_sanitize_queries


def test_trim_and_dedupe() -> None:
    result = validate_and_sanitize_queries(["  foo  ", "foo", "bar"])
    assert result.queries == ["foo", "bar"]


def test_email_redaction() -> None:
    result = validate_and_sanitize_queries(["john@example.com 기반 서비스"])
    assert "[EMAIL]" in result.queries[0]
    assert result.notes[0].changed is True


def test_phone_redaction() -> None:
    result = validate_and_sanitize_queries(["연락처 010-1234-5678 사례"])
    assert "[PHONE]" in result.queries[0]


def test_ipv4_redaction() -> None:
    result = validate_and_sanitize_queries(["서버 192.168.0.1 배포"])
    assert "[IP]" in result.queries[0]


def test_uuid_redaction() -> None:
    result = validate_and_sanitize_queries(
        ["세션 550e8400-e29b-41d4-a716-446655440000 관련"]
    )
    assert "[UUID]" in result.queries[0]


def test_empty_after_redaction_invalid() -> None:
    with pytest.raises(AppError) as exc:
        validate_and_sanitize_queries(["john@example.com"])
    assert exc.value.code == "WEB_SEARCH_QUERY_INVALID"


def test_max_count() -> None:
    with pytest.raises(AppError) as exc:
        validate_and_sanitize_queries([f"q{i}" for i in range(6)])
    assert exc.value.code == "WEB_SEARCH_QUERY_INVALID"


def test_max_length() -> None:
    with pytest.raises(AppError) as exc:
        validate_and_sanitize_queries(["x" * 201])
    assert exc.value.code == "WEB_SEARCH_QUERY_INVALID"
