#!/usr/bin/env python3
"""Evaluate Idea search ranking quality (Step 25).

Uses production list_* / RRF merge paths with injectable RRF K.
Seeds a labeled corpus into TEST_DATABASE_URL only.

Embedding modes:
  topic       — TopicAwareEvalEmbeddingProvider (deterministic CI / regression)
  configured  — production get_embedding_provider (e.g. real BAAI/bge-m3)
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


def _configure_eval_env(*, embedding_mode: str) -> None:
    if not TEST_DATABASE_URL:
        raise SystemExit(
            "TEST_DATABASE_URL is required. Refusing to evaluate against shared DATABASE_URL."
        )
    assert_configured_test_database_safe()
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["EMBEDDING_ENABLED"] = "true"
    os.environ["EMBEDDING_MODEL_NAME"] = os.environ.get(
        "EMBEDDING_MODEL_NAME", "BAAI/bge-m3"
    )
    os.environ["EMBEDDING_DIMENSION"] = os.environ.get("EMBEDDING_DIMENSION", "1024")
    os.environ["APP_ENV"] = os.environ.get("APP_ENV", "development")
    os.environ["AI_WORKER_ENABLED"] = "false"
    os.environ["EMBEDDING_WORKER_ENABLED"] = "false"

    mode = embedding_mode.strip().lower()
    if mode == "topic":
        # Force offline fake settings for Settings validation; vectors come from
        # TopicAwareEvalEmbeddingProvider, not the configured HTTP provider.
        os.environ["EMBEDDING_PROVIDER"] = "fake"
        os.environ["EMBEDDING_API_URL"] = (
            os.environ.get("EMBEDDING_API_URL") or "http://embed.eval.local"
        )
    elif mode == "configured":
        # Preserve caller-provided production embedding settings.
        provider = os.environ.get("EMBEDDING_PROVIDER", "").strip() or "openai_compatible"
        os.environ["EMBEDDING_PROVIDER"] = provider
        api_url = os.environ.get("EMBEDDING_API_URL", "").strip()
        if not api_url:
            raise SystemExit(
                "configured mode requires EMBEDDING_API_URL "
                "(OpenAI-compatible BGE endpoint)."
            )
    else:
        raise SystemExit(f"Unknown --embedding-mode {embedding_mode!r}")

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
    embedding_mode: str,
    quiet: bool = False,
    reuse_db_ctx: tuple | None = None,
) -> dict:
    from app.core.config import get_settings

    cases = load_cases(cases_path)
    owns_session = reuse_db_ctx is None
    if reuse_db_ctx is None:
        SessionLocal, engine = _session_factory()
        db = SessionLocal()
        ctx = seed_eval_corpus(
            db, settings=get_settings(), embedding_mode=embedding_mode
        )
    else:
        db, ctx, engine = reuse_db_ctx

    try:
        results = evaluate_cases(
            db,
            ctx=ctx,
            cases=cases,
            top_k=top_k,
            settings=get_settings(),
            rrf_k=rrf_k,
            candidate_limit=candidate_limit,
            embedding_mode=embedding_mode,
        )
        summary = summarize(results)
        by_cat = summarize_by_category(results)
        payload = {
            "workspace_id": str(ctx.workspace_id),
            "embedding_mode": embedding_mode,
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
            print(f"embedding_mode={embedding_mode}")
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
        if owns_session:
            db.close()
            engine.dispose()


def sweep_rrf_k(
    *, cases_path: Path, top_k: int, ks: list[int], embedding_mode: str
) -> None:
    from app.core.config import get_settings

    print(f"## RRF K sweep (hybrid metrics, embedding_mode={embedding_mode})\n")
    print(f"{'K':>5} {'Hit@5':>7} {'MRR':>7} {'nDCG@5':>8} {'ExactTop1':>10}")
    # Seed once so configured/BGE does not re-embed the corpus for every K.
    SessionLocal, engine = _session_factory()
    db = SessionLocal()
    try:
        ctx = seed_eval_corpus(
            db, settings=get_settings(), embedding_mode=embedding_mode
        )
        reuse = (db, ctx, engine)
        for k in ks:
            payload = run_once(
                cases_path=cases_path,
                top_k=top_k,
                rrf_k=k,
                candidate_limit=None,
                json_out=None,
                embedding_mode=embedding_mode,
                quiet=True,
                reuse_db_ctx=reuse,
            )
            hybrid = payload["summary"]["hybrid"]
            exact = hybrid["exact_top1"]
            exact_s = f"{exact:.3f}" if exact == exact else "n/a"
            print(
                f"{k:>5} {hybrid['hit@5']:7.3f} {hybrid['mrr']:7.3f} "
                f"{hybrid['ndcg@5']:8.3f} {exact_s:>10}"
            )
    finally:
        db.close()
        engine.dispose()


def sweep_candidates(
    *,
    cases_path: Path,
    top_k: int,
    sizes: list[int],
    rrf_k: int,
    embedding_mode: str,
) -> None:
    print(
        f"## Candidate limit sweep (hybrid, RRF_K={rrf_k}, "
        f"embedding_mode={embedding_mode})\n"
    )
    print(
        "NOTE: with corpus size < 50, candidate 50/100/200/300 cannot discriminate "
        "production window quality; results are informational only.\n"
    )
    print(
        f"{'Cand':>5} {'Hit@5':>7} {'MRR':>7} {'nDCG@5':>8} "
        f"{'ExactTop1':>10} {'p50ms':>8}"
    )
    from app.core.config import get_settings

    SessionLocal, engine = _session_factory()
    db = SessionLocal()
    try:
        ctx = seed_eval_corpus(
            db, settings=get_settings(), embedding_mode=embedding_mode
        )
        reuse = (db, ctx, engine)
        for size in sizes:
            payload = run_once(
                cases_path=cases_path,
                top_k=top_k,
                rrf_k=rrf_k,
                candidate_limit=size,
                json_out=None,
                embedding_mode=embedding_mode,
                quiet=True,
                reuse_db_ctx=reuse,
            )
            hybrid = payload["summary"]["hybrid"]
            exact = hybrid["exact_top1"]
            exact_s = f"{exact:.3f}" if exact == exact else "n/a"
            print(
                f"{size:>5} {hybrid['hit@5']:7.3f} {hybrid['mrr']:7.3f} "
                f"{hybrid['ndcg@5']:8.3f} {exact_s:>10} "
                f"{hybrid['latency_p50_ms']:8.1f}"
            )
    finally:
        db.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate IdeaFlow search ranking quality"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--rrf-k", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=None)
    parser.add_argument(
        "--embedding-mode",
        choices=("topic", "configured"),
        default="topic",
        help="topic=deterministic harness; configured=production embedding provider",
    )
    parser.add_argument("--sweep-rrf-k", action="store_true")
    parser.add_argument("--sweep-candidates", action="store_true")
    parser.add_argument("--rrf-k-values", type=str, default="10,20,40,60,80,100")
    parser.add_argument("--candidate-values", type=str, default="50,100,200,300")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    _configure_eval_env(embedding_mode=args.embedding_mode)

    if args.sweep_rrf_k:
        ks = [int(x.strip()) for x in args.rrf_k_values.split(",") if x.strip()]
        sweep_rrf_k(
            cases_path=args.cases,
            top_k=args.top_k,
            ks=ks,
            embedding_mode=args.embedding_mode,
        )
        return 0
    if args.sweep_candidates:
        sizes = [int(x.strip()) for x in args.candidate_values.split(",") if x.strip()]
        rrf_k = args.rrf_k if args.rrf_k is not None else 60
        sweep_candidates(
            cases_path=args.cases,
            top_k=args.top_k,
            sizes=sizes,
            rrf_k=rrf_k,
            embedding_mode=args.embedding_mode,
        )
        return 0

    run_once(
        cases_path=args.cases,
        top_k=args.top_k,
        rrf_k=args.rrf_k,
        candidate_limit=args.candidate_limit,
        json_out=args.json_out,
        embedding_mode=args.embedding_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
