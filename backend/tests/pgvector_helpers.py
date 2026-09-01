"""pgvector / embedding integration test helpers."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

requires_database = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping PostgreSQL integration tests",
)


def pgvector_available() -> bool:
    if not DATABASE_URL:
        return False
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
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
    not pgvector_available(),
    reason="pgvector extension not available in DATABASE_URL PostgreSQL",
)
