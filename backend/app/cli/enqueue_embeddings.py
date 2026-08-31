"""Enqueue embedding jobs for existing Ideas."""

from __future__ import annotations

import argparse
import sys
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.embedding_service import scan_ideas_for_enqueue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enqueue Idea embedding jobs")
    parser.add_argument("--all", action="store_true", help="Scan all non-deleted ideas")
    parser.add_argument("--workspace-id", type=str, default=None, help="Limit to one workspace UUID")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enqueue even when current embedding matches",
    )
    args = parser.parse_args(argv)

    if not args.all and args.workspace_id is None:
        parser.error("Specify --all and/or --workspace-id")

    settings = get_settings()
    workspace_id = UUID(args.workspace_id) if args.workspace_id else None
    factory = get_session_factory()

    with factory() as db:
        scanned, already_current, queued = scan_ideas_for_enqueue(
            db,
            workspace_id=workspace_id,
            force=args.force,
            settings=settings,
        )
        db.commit()

    print(f"scanned={scanned} already_current={already_current} queued={queued}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
