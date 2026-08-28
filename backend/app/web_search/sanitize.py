"""Deterministic search query sanitization (Step 9)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Settings, get_settings

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/=_-]{48,}\b")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_REDACTIONS = (
    (_EMAIL_RE, "[EMAIL]"),
    (_IPV4_RE, "[IP]"),
    (_UUID_RE, "[UUID]"),
    (_PHONE_RE, "[PHONE]"),
    (_TOKEN_RE, "[TOKEN]"),
)

_MEANINGLESS_ONLY = re.compile(r"^(\[(?:EMAIL|PHONE|IP|UUID|TOKEN)\]\s*)+$")


@dataclass(frozen=True)
class SanitizationNote:
    query_index: int
    changed: bool


@dataclass(frozen=True)
class SanitizedQuerySet:
    queries: list[str]
    notes: list[SanitizationNote]


def _sanitize_one(text: str) -> tuple[str, bool]:
    original = text
    cleaned = _CONTROL_RE.sub("", text).strip()
    changed = cleaned != original
    for pattern, replacement in _REDACTIONS:
        new = pattern.sub(replacement, cleaned)
        if new != cleaned:
            changed = True
            cleaned = new
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, changed


def _is_meaningful(query: str) -> bool:
    if not query:
        return False
    if _MEANINGLESS_ONLY.match(query):
        return False
    return True


def validate_and_sanitize_queries(
    raw_queries: list[str],
    *,
    settings: Settings | None = None,
) -> SanitizedQuerySet:
    """Validate user queries and return sanitized queries_to_send."""
    from app.core.errors import AppError

    cfg = settings or get_settings()
    max_queries = cfg.web_search_max_queries
    max_len = 200

    if not raw_queries:
        raise AppError(
            "At least one search query is required.",
            code="WEB_SEARCH_QUERY_INVALID",
            status_code=400,
        )

    seen: set[str] = set()
    sanitized: list[str] = []
    notes: list[SanitizationNote] = []

    for raw in raw_queries:
        trimmed = (raw or "").strip()
        if not trimmed:
            continue
        if len(trimmed) > max_len:
            raise AppError(
                f"Each query must be at most {max_len} characters.",
                code="WEB_SEARCH_QUERY_INVALID",
                status_code=400,
            )
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned, changed = _sanitize_one(trimmed)
        if not _is_meaningful(cleaned):
            raise AppError(
                "Search query is invalid after sanitization.",
                code="WEB_SEARCH_QUERY_INVALID",
                status_code=400,
            )
        sanitized.append(cleaned)
        notes.append(SanitizationNote(query_index=len(sanitized) - 1, changed=changed))

    if not sanitized:
        raise AppError(
            "At least one non-empty search query is required.",
            code="WEB_SEARCH_QUERY_INVALID",
            status_code=400,
        )
    if len(sanitized) > max_queries:
        raise AppError(
            f"At most {max_queries} search queries are allowed.",
            code="WEB_SEARCH_QUERY_INVALID",
            status_code=400,
        )
    return SanitizedQuerySet(queries=sanitized, notes=notes)
