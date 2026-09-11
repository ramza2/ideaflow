"""Shared pytest hooks for database-backed tests."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import create_engine, text

from tests.db_test_safety import (
    TEST_DATABASE_URL,
    UnsafeTestDatabaseError,
    assert_configured_test_database_safe,
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def _ensure_pgvector_migrations() -> None:
    """Apply migrations on the dedicated TEST database when configured.

    Never touches ``DATABASE_URL`` / the shared development database.

    If ``TEST_DATABASE_URL`` is set but unsafe (dev DB name / same as
    ``DATABASE_URL``), fail the session immediately — do not skip.
    """
    if not TEST_DATABASE_URL:
        return

    # Fail-fast: misconfigured TEST_DATABASE_URL must not become a quiet skip.
    assert_configured_test_database_safe()

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except UnsafeTestDatabaseError:
        raise
    except Exception as exc:  # pragma: no cover - env-specific connectivity
        logger.warning("Skipping test-DB migration bootstrap: %s", exc)
        engine.dispose()
        return

    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
        command.upgrade(cfg, "head")
    except UnsafeTestDatabaseError:
        raise
    except Exception as exc:  # pragma: no cover - env-specific
        logger.warning("alembic upgrade on TEST_DATABASE_URL failed: %s", exc)
        engine.dispose()
        return
    finally:
        engine.dispose()

    try:
        from app.services import embedding_service

        embedding_service._EMBEDDING_STORAGE_READY = None
    except Exception:
        pass
