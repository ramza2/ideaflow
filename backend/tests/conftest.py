"""Shared pytest hooks for database-backed tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture(scope="session", autouse=True)
def _ensure_pgvector_migrations() -> None:
    """Apply Step 13 migrations when pgvector is available."""
    if not DATABASE_URL:
        return

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception:
        engine.dispose()
        return

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")
    engine.dispose()

    # Reset cached table probe after migration.
    from app.services import embedding_service

    embedding_service._EMBEDDING_STORAGE_READY = None
