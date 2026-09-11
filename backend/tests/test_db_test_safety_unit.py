"""Unit tests for dedicated TEST_DATABASE_URL safety guards."""

from __future__ import annotations

import pytest

from tests.db_test_safety import (
    UnsafeTestDatabaseError,
    assert_safe_test_database_url,
    is_safe_test_database_name,
    normalize_db_endpoint,
    redact_database_url,
    urls_point_to_same_database,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ideaflow_test", True),
        ("test_ideaflow", True),
        ("ideaflow-test", True),
        ("ideaflow_test_ci", True),
        ("ideaflow-test-ci", True),
        ("ideaflow", False),
        ("contest", False),
        ("latest", False),
        ("production", False),
        ("", False),
    ],
)
def test_safe_test_database_name(name: str, expected: bool) -> None:
    assert is_safe_test_database_name(name) is expected


def test_driver_difference_still_same_database() -> None:
    left = "postgresql://ideaflow:x@localhost:5432/ideaflow"
    right = "postgresql+psycopg://ideaflow:y@localhost:5432/ideaflow"
    assert urls_point_to_same_database(left, right) is True
    assert normalize_db_endpoint(left) == ("localhost", 5432, "ideaflow")


def test_default_port_treated_as_5432() -> None:
    with_port = "postgresql+psycopg://u:p@db.example:5432/ideaflow_test"
    without_port = "postgresql+psycopg://u:p@db.example/ideaflow_test"
    assert urls_point_to_same_database(with_port, without_port) is True


def test_different_database_names_are_not_same() -> None:
    left = "postgresql+psycopg://u:p@localhost:5432/ideaflow"
    right = "postgresql+psycopg://u:p@localhost:5432/ideaflow_test"
    assert urls_point_to_same_database(left, right) is False


def test_redact_omits_password() -> None:
    redacted = redact_database_url(
        "postgresql+psycopg://ideaflow:s3cret@localhost:5432/ideaflow_test"
    )
    assert "s3cret" not in redacted
    assert "ideaflow_test" in redacted
    assert "localhost" in redacted


def test_assert_safe_rejects_dev_database_name() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database_url(
            "postgresql+psycopg://ideaflow:x@localhost:5432/ideaflow",
            label="TEST_DATABASE_URL",
        )


def test_assert_safe_allows_ideaflow_test_when_protected_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.db_test_safety as safety

    monkeypatch.setattr(
        safety,
        "_PROTECTED_DATABASE_URL",
        "postgresql+psycopg://ideaflow:x@localhost:5432/ideaflow",
    )
    assert_safe_test_database_url(
        "postgresql+psycopg://ideaflow:x@localhost:5432/ideaflow_test"
    )


def test_assert_safe_rejects_same_database_as_protected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.db_test_safety as safety

    monkeypatch.setattr(
        safety,
        "_PROTECTED_DATABASE_URL",
        "postgresql://ideaflow:old@localhost/ideaflow_test",
    )
    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database_url(
            "postgresql+psycopg://ideaflow:new@localhost:5432/ideaflow_test",
            label="TEST_DATABASE_URL",
        )


class _FakeEngine:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeConn:
    def __init__(self, url: str) -> None:
        self.engine = _FakeEngine(url)
        self.executed = False

    def execute(self, *_args, **_kwargs):
        self.executed = True
        return None


def test_destructive_guard_rejects_before_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.db_test_safety as safety
    from tests.pgvector_helpers import wipe_embedding_tables

    monkeypatch.setattr(safety, "_PROTECTED_DATABASE_URL", "")
    conn = _FakeConn("postgresql+psycopg://ideaflow:x@localhost:5432/ideaflow")

    with pytest.raises(UnsafeTestDatabaseError):
        wipe_embedding_tables(conn)

    assert conn.executed is False


def test_destructive_guard_allows_safe_test_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.db_test_safety as safety
    from tests.pgvector_helpers import wipe_embedding_tables

    monkeypatch.setattr(
        safety,
        "_PROTECTED_DATABASE_URL",
        "postgresql+psycopg://ideaflow:x@localhost:5432/ideaflow",
    )
    conn = _FakeConn(
        "postgresql+psycopg://ideaflow:x@localhost:5432/ideaflow_test"
    )

    wipe_embedding_tables(conn)
    assert conn.executed is True
