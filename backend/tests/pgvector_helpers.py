"""pgvector / embedding integration test helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests.db_test_safety import (
    TEST_DATABASE_URL,
    assert_test_database_safe,
    require_test_database_url,
    requires_test_database,
)

# Backwards-compatible alias used by older imports in this suite.
# Integration tests must use TEST_DATABASE_URL — never fall back to DATABASE_URL.
DATABASE_URL = TEST_DATABASE_URL

requires_database = requires_test_database

_EMBEDDING_TRUNCATE_SQL = (
    "TRUNCATE idea_embedding_jobs, idea_embeddings, "
    "integration_config_audits, integration_runtime_configs CASCADE"
)


def wipe_embedding_tables(execute_target) -> None:
    """Truncate embedding tables for integration-test isolation.

    Refuses to run unless the bound engine/URL is a dedicated test database.
    """
    assert_test_database_safe(execute_target)
    execute_target.execute(text(_EMBEDDING_TRUNCATE_SQL))


def pgvector_available() -> bool:
    if not TEST_DATABASE_URL:
        return False
    # Unsafe TEST_DATABASE_URL must fail loudly via session fixture / callers —
    # do not hide it behind a skip by returning False here.
    assert_test_database_safe(TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            return version is not None
    except Exception:
        return False
    finally:
        engine.dispose()


requires_pgvector = pytest.mark.skipif(
    not TEST_DATABASE_URL or not pgvector_available(),
    reason="pgvector extension not available in TEST_DATABASE_URL PostgreSQL",
)


def integration_database_url() -> str:
    """Resolved TEST_DATABASE_URL after safety checks (skips when unset)."""
    return require_test_database_url()
