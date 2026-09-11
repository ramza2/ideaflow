"""Dedicated test-DB safety guards for IdeaFlow integration tests.

Integration suites may TRUNCATE/DELETE tables. They must never target the
application / shared / development database.

Rules
-----
* Integration tests connect via ``TEST_DATABASE_URL`` only (no fallback to
  ``DATABASE_URL``).
* The test database name must contain an explicit ``test`` marker
  (e.g. ``ideaflow_test``, ``test_ideaflow``, ``ideaflow-test-ci``).
* ``TEST_DATABASE_URL`` must not resolve to the same host/port/database as
  the protected application ``DATABASE_URL`` (captured at import time).
* Destructive helpers call :func:`assert_test_database_safe` before SQL.

Credentials are never logged.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import unquote

import pytest
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import Session

# Captured once at import — before pytest monkeypatch rewrites DATABASE_URL to
# the test URL so the app-under-test talks to ideaflow_test.
_PROTECTED_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

# Name must look like a dedicated test database — not incidental "test" substrings
# such as ``contest`` or ``latest``.
_SAFE_TEST_DB_NAME = re.compile(
    r"(^test[_-])|([_-]test$)|([_-]test[_-])",
    re.IGNORECASE,
)

_UNSAFE_MSG = (
    "Unsafe integration-test database refused.\n\n"
    "Integration tests may TRUNCATE / DELETE tables and must not use the "
    "application or shared development database.\n\n"
    "Configure a dedicated TEST_DATABASE_URL such as:\n"
    "  postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow_test\n\n"
    "See docs/testing.md."
)


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when a destructive fixture would touch a non-test database."""


def protected_database_url() -> str:
    """Application / shared DB URL protected from destructive fixtures."""
    return _PROTECTED_DATABASE_URL


def _as_url(value: str | URL) -> URL:
    if isinstance(value, URL):
        return value
    return make_url(value)


def database_name_from_url(url: str | URL) -> str:
    parsed = _as_url(url)
    name = parsed.database or ""
    return unquote(name)


def is_safe_test_database_name(name: str) -> bool:
    """Return True when *name* is an explicit dedicated test database."""
    if not name:
        return False
    return _SAFE_TEST_DB_NAME.search(name) is not None


def normalize_db_endpoint(url: str | URL) -> tuple[str, int | None, str]:
    """Return (host, port, database) for equality checks (ignore driver/user/pass)."""
    parsed = _as_url(url)
    host = (parsed.host or "").lower()
    port = parsed.port
    if port is None and host:
        # SQLAlchemy omits default 5432; treat missing as 5432 for postgres.
        backend = (parsed.get_backend_name() or "").lower()
        if backend.startswith("postgresql") or backend == "postgres":
            port = 5432
    database = database_name_from_url(parsed).lower()
    return host, port, database


def urls_point_to_same_database(left: str | URL, right: str | URL) -> bool:
    """True when both URLs address the same host/port/database."""
    if not left or not right:
        return False
    try:
        return normalize_db_endpoint(left) == normalize_db_endpoint(right)
    except Exception:
        return False


def redact_database_url(url: str | URL) -> str:
    """Human-readable location without credentials."""
    parsed = _as_url(url)
    host = parsed.host or "?"
    port = parsed.port
    port_s = f":{port}" if port is not None else ""
    name = database_name_from_url(parsed) or "?"
    return f"{host}{port_s}/{name}"


def _render_url(url_obj: Any) -> str | None:
    if isinstance(url_obj, str):
        return url_obj.strip()
    if isinstance(url_obj, URL):
        return url_obj.render_as_string(hide_password=False)
    render = getattr(url_obj, "render_as_string", None)
    if callable(render):
        try:
            return str(render(hide_password=False))
        except TypeError:
            return str(render())
    return None


def _url_from_target(target: Any, *, _seen: set[int] | None = None) -> str:
    if target is None:
        raise UnsafeTestDatabaseError("No database target provided for safety check")
    seen = _seen if _seen is not None else set()
    target_id = id(target)
    if target_id in seen:
        raise UnsafeTestDatabaseError("Cannot resolve database URL (cyclic target)")
    seen.add(target_id)

    if isinstance(target, str):
        return target.strip()
    if isinstance(target, URL):
        return target.render_as_string(hide_password=False)
    if isinstance(target, Engine):
        rendered = _render_url(target.url)
        if rendered:
            return rendered
    if isinstance(target, Connection):
        rendered = _render_url(target.engine.url)
        if rendered:
            return rendered
    if isinstance(target, Session):
        return _url_from_target(target.get_bind(), _seen=seen)

    rendered = _render_url(getattr(target, "url", None))
    if rendered:
        return rendered

    for attr in ("engine", "connection", "bind"):
        try:
            inner = object.__getattribute__(target, attr)
        except AttributeError:
            continue
        if inner is not None and inner is not target:
            try:
                return _url_from_target(inner, _seen=seen)
            except UnsafeTestDatabaseError:
                continue
    raise UnsafeTestDatabaseError(
        f"Cannot resolve database URL from target type {type(target).__name__}"
    )


def assert_safe_test_database_url(url: str | URL, *, label: str = "database") -> None:
    """Fail fast when *url* is not a dedicated test database."""
    if not url or (isinstance(url, str) and not url.strip()):
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is empty. Configure a dedicated *_test database.\n"
            "See docs/testing.md."
        )

    name = database_name_from_url(url)
    location = redact_database_url(url)

    if not is_safe_test_database_name(name):
        raise UnsafeTestDatabaseError(
            f"{_UNSAFE_MSG}\n"
            f"{label} points to: {location}\n"
            f"Database name '{name}' does not look like a dedicated test DB "
            f"(expected marker such as ideaflow_test / test_ideaflow)."
        )

    protected = protected_database_url()
    if protected and urls_point_to_same_database(url, protected):
        raise UnsafeTestDatabaseError(
            f"{_UNSAFE_MSG}\n"
            f"{label} points to the same host/port/database as DATABASE_URL:\n"
            f"  {location}\n"
            "Set TEST_DATABASE_URL to a different database (e.g. ideaflow_test)."
        )


def assert_test_database_safe(target: Any) -> None:
    """Guard used immediately before destructive SQL."""
    url = _url_from_target(target)
    assert_safe_test_database_url(url, label="Destructive fixture target")


def assert_configured_test_database_safe() -> None:
    """Validate ``TEST_DATABASE_URL`` itself (session / fixture entry)."""
    assert_safe_test_database_url(TEST_DATABASE_URL, label="TEST_DATABASE_URL")


requires_test_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "TEST_DATABASE_URL not set — skipping PostgreSQL integration tests "
        "(refusing to use DATABASE_URL / shared DB)"
    ),
)


def require_test_database_url() -> str:
    """Return TEST_DATABASE_URL or skip the calling test."""
    if not TEST_DATABASE_URL:
        pytest.skip(
            "TEST_DATABASE_URL not set — skipping PostgreSQL integration tests "
            "(refusing to use DATABASE_URL / shared DB)"
        )
    assert_configured_test_database_safe()
    return TEST_DATABASE_URL
