"""Enqueue embedding jobs for existing Ideas."""

from __future__ import annotations

import argparse
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.embedding_service import (
    embedding_coverage_counts,
    scan_ideas_for_enqueue,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enqueue Idea embedding jobs")
    parser.add_argument("--all", action="store_true", help="Scan all non-deleted ideas")
    parser.add_argument("--workspace-id", type=str, default=None, help="Limit to one workspace UUID")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enqueue even when current embedding matches",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max ideas to consider (ordered by idea id)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count ideas that would be queued without writing jobs",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Print embedding coverage counters and exit",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    if not args.coverage and not args.all and args.workspace_id is None:
        parser.error("Specify --all and/or --workspace-id (or --coverage)")

    settings = get_settings()
    workspace_id = UUID(args.workspace_id) if args.workspace_id else None
    factory = get_session_factory()

    with factory() as db:
        if args.coverage:
            counts = embedding_coverage_counts(db, workspace_id=workspace_id)
            total = counts["total"]
            with_emb = counts["with_embedding"]
            missing = counts["without_embedding"]
            pct = (100.0 * with_emb / total) if total else 0.0
            print(
                "coverage "
                f"total={total} with_embedding={with_emb} without_embedding={missing} "
                f"percent={pct:.1f} "
                f"jobs_queued={counts['jobs_queued']} jobs_running={counts['jobs_running']} "
                f"jobs_succeeded={counts['jobs_succeeded']} jobs_failed={counts['jobs_failed']}"
            )
            if not args.all and args.workspace_id is None:
                return 0

        scanned, already_current, queued = scan_ideas_for_enqueue(
            db,
            workspace_id=workspace_id,
            force=args.force,
            settings=settings,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            db.commit()

    prefix = "dry_run " if args.dry_run else ""
    print(f"{prefix}scanned={scanned} already_current={already_current} queued={queued}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
