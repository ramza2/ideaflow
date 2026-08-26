"""CLI: ensure PERSONAL workspaces for existing users (maintenance backfill)."""

from __future__ import annotations

import sys

from app.core.logging import setup_logging
from app.db.session import get_session_factory, reset_engine
from app.services.workspace import backfill_personal_workspaces


def main() -> int:
    setup_logging("INFO")
    print("IdeaFlow — ensure personal workspaces")
    reset_engine()
    session = get_session_factory()()
    try:
        result = backfill_personal_workspaces(session)
        session.commit()
        print(
            f"created: {result.created}\n"
            f"existing: {result.existing}\n"
            f"failed: {result.failed}"
        )
        return 1 if result.failed else 0
    except Exception as exc:
        session.rollback()
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
