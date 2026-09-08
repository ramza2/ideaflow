"""pgvector / embedding integration test helpers."""

from __future__ import annotations

import os
import warnings

import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

requires_database = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping PostgreSQL integration tests",
)

_EMBEDDING_TRUNCATE_SQL = (
    "TRUNCATE idea_embedding_jobs, idea_embeddings, "
    "integration_config_audits, integration_runtime_configs CASCADE"
)


def wipe_embedding_tables(execute_target) -> None:
    """Truncate embedding tables for integration-test isolation.

    Integration suites historically wipe *all* embedding rows. When
    ``DATABASE_URL`` points at a shared/dev DB used by a live app/worker,
    coverage drops to ~0% until ``python -m app.cli.enqueue_embeddings --all``
    re-queues missing ideas. Prefer a dedicated test database in CI.
    """
    warnings.warn(
        "Wiping idea_embeddings / idea_embedding_jobs on DATABASE_URL "
        "(shared DB will need enqueue_embeddings --all afterwards)",
        UserWarning,
        stacklevel=2,
    )
    # Session.execute or Connection.execute
    execute_target.execute(text(_EMBEDDING_TRUNCATE_SQL))


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
