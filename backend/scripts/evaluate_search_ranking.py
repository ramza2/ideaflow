#!/usr/bin/env python3
"""Evaluate Idea search ranking quality (Step 25).

Uses production list_* / RRF merge paths with injectable RRF K.
Seeds a labeled corpus into TEST_DATABASE_URL only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.db_test_safety import (
    TEST_DATABASE_URL,
    assert_configured_test_database_safe,
    assert_test_database_safe,
)
from tests.search_quality.runner import (
    DEFAULT_CASES_PATH,
    evaluate_cases,
    format_summary_table,
    load_cases,
    seed_eval_corpus,
    summarize,
    summarize_by_category,
)


def _configure_eval_env() -> None:
    if not TEST_DATABASE_URL:
        raise SystemExit(
            "TEST_DATABASE_URL is required. Refusing to evaluate against shared DATABASE_URL."
        )
    assert_configured_test_database_safe()
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["EMBEDDING_ENABLED"] = "true"
    os.environ["EMBEDDING_PROVIDER"] = "fake"
    os.environ["EMBEDDING_API_URL"] = os.environ.get("EMBEDDING_API_URL") or "http://embed.eval.local"
    os.environ["EMBEDDING_MODEL_NAME"] = "BAAI/bge-m3"
    os.environ["EMBEDDING_DIMENSION"] = "1024"
    os.environ["APP_ENV"] = "development"
    os.environ["AI_WORKER_ENABLED"] = "false"
    os.environ["EMBEDDING_WORKER_ENABLED"] = "false"

    from app.core.config import get_settings
    from app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()


def _session_factory():
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    assert_test_database_safe(engine)
    return sessionmaker(bind=engine, expire_on_commit=False), engine


def _print_failures(results, *, limit: int = 12) -> None:
    print("\n## Notable misses (Hit@5 == 0 or Exact Top1 fail)")
    shown = 0
    for row in results:
        exact_fail = row.exact_top1 is not None and row.exact_top1 < 1.0
        if row.hit5 >= 1.0 and not exact_fail:
            continue
        print(
            f"- [{row.mode}] {row.case_id} q={row.query!r} "
            f"hit5={row.hit5:.0f} exact={row.exact_top1} ranked={row.ranked[:5]}"
        )
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        print("- none")


def run_once(
    *,
    cases_path: Path,
    top_k: int,
    rrf_k: int | None,
    candidate_limit: int | None,
    json_out: Path | None,
    quiet: bool = False,
) -> dict:
    from app.core.config import get_settings

    cases = load_cases(cases_path)
    SessionLocal, engine = _session_factory()
    db = SessionLocal()
    try:
        ctx = seed_eval_corpus(db, settings=get_settings())
        results = evaluate_cases(
            db,
            ctx=ctx,
            cases=cases,
            top_k=top_k,
            settings=get_settings(),
            rrf_k=rrf_k,
            candidate_limit=candidate_limit,
        )
        summary = summarize(results)
        by_cat = summarize_by_category(results)
        payload = {
            "workspace_id": str(ctx.workspace_id),
            "rrf_k": rrf_k,
            "candidate_limit": candidate_limit,
            "top_k": top_k,
            "summary": summary,
            "by_category": by_cat,
            "results": [
                {
                    "case_id": r.case_id,
                    "category": r.category,
                    "query": r.query,
                    "mode": r.mode,
                    "ranked": r.ranked,
                    "hit@5": r.hit5,
                    "mrr": r.mrr,
                    "ndcg@5": r.ndcg5,
                    "exact_top1": r.exact_top1,
                    "latency_ms": r.latency_ms,
                }
                for r in results
            ],
        }
        if not quiet:
            print(format_summary_table(summary))
            print("\n## By category (nDCG@5)")
            for category, modes in sorted(by_cat.items()):
                parts = [
                    f"{mode}={modes[mode]['ndcg@5']:.3f}"
                    for mode in ("keyword", "semantic", "hybrid")
                    if mode in modes
                ]
                print(f"- {category}: " + ", ".join(parts))
            _print_failures(results)
        if json_out:
            json_out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if not quiet:
                print(f"\nWrote {json_out}")
        return payload
    finally:
        db.close()
        engine.dispose()


def sweep_rrf_k(*, cases_path: Path, top_k: int, ks: list[int]) -> None:
    print("## RRF K sweep (hybrid metrics)\n")
    print(f"{'K':>5} {'Hit@5':>7} {'MRR':>7} {'nDCG@5':>8} {'ExactTop1':>10}")
    for k in ks:
        payload = run_once(
            cases_path=cases_path,
            top_k=top_k,
            rrf_k=k,
            candidate_limit=None,
            json_out=None,
            quiet=True,
        )
        hybrid = payload["summary"]["hybrid"]
        exact = hybrid["exact_top1"]
        exact_s = f"{exact:.3f}" if exact == exact else "n/a"
        print(
            f"{k:>5} {hybrid['hit@5']:7.3f} {hybrid['mrr']:7.3f} "
            f"{hybrid['ndcg@5']:8.3f} {exact_s:>10}"
        )


def sweep_candidates(
    *, cases_path: Path, top_k: int, sizes: list[int], rrf_k: int
) -> None:
    print(f"## Candidate limit sweep (hybrid, RRF_K={rrf_k})\n")
    print(
        f"{'Cand':>5} {'Hit@5':>7} {'MRR':>7} {'nDCG@5':>8} "
        f"{'ExactTop1':>10} {'p50ms':>8}"
    )
    for size in sizes:
        payload = run_once(
            cases_path=cases_path,
            top_k=top_k,
            rrf_k=rrf_k,
            candidate_limit=size,
            json_out=None,
            quiet=True,
        )
        hybrid = payload["summary"]["hybrid"]
        exact = hybrid["exact_top1"]
        exact_s = f"{exact:.3f}" if exact == exact else "n/a"
        print(
            f"{size:>5} {hybrid['hit@5']:7.3f} {hybrid['mrr']:7.3f} "
            f"{hybrid['ndcg@5']:8.3f} {exact_s:>10} "
            f"{hybrid['latency_p50_ms']:8.1f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate IdeaFlow search ranking quality"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--rrf-k", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=None)
    parser.add_argument("--sweep-rrf-k", action="store_true")
    parser.add_argument("--sweep-candidates", action="store_true")
    parser.add_argument("--rrf-k-values", type=str, default="10,20,40,60,80,100")
    parser.add_argument("--candidate-values", type=str, default="50,100,200,300")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    _configure_eval_env()

    if args.sweep_rrf_k:
        ks = [int(x.strip()) for x in args.rrf_k_values.split(",") if x.strip()]
        sweep_rrf_k(cases_path=args.cases, top_k=args.top_k, ks=ks)
        return 0
    if args.sweep_candidates:
        sizes = [int(x.strip()) for x in args.candidate_values.split(",") if x.strip()]
        rrf_k = args.rrf_k if args.rrf_k is not None else 60
        sweep_candidates(
            cases_path=args.cases, top_k=args.top_k, sizes=sizes, rrf_k=rrf_k
        )
        return 0

    run_once(
        cases_path=args.cases,
        top_k=args.top_k,
        rrf_k=args.rrf_k,
        candidate_limit=args.candidate_limit,
        json_out=args.json_out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
