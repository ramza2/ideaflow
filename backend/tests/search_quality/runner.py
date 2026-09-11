"""Seed eval corpus and run ranking against production list_* APIs."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.embeddings.canonical import build_idea_embedding_text, compute_content_hash
from app.models.collaboration import IdeaComment, IdeaReviewRequest, Notification
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import (
    IdeaVisibility,
    SystemRole,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.relations import IdeaParticipant, IdeaShare, IdeaTag
from app.models.user import User
from app.models.validation import IdeaValidation
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceStage
from app.schemas.idea import IdeaCreate
from app.services import idea as idea_service
from app.services import idea_search
from app.services.workspace import seed_workspace_defaults
from tests.search_quality.corpus import SEARCH_RANKING_CORPUS
from tests.search_quality.metrics import exact_top1, hit_at_k, mean, mrr, ndcg_at_k
from tests.search_quality.topic_embedding import (
    TopicAwareEvalEmbeddingProvider,
    extract_idea_code,
)

EVAL_WORKSPACE_NAME = "search-ranking-eval"
EVAL_OWNER_EMAIL = "search-ranking-eval@example.com"
DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "search_ranking_cases.json"
)


@dataclass
class EvalContext:
    workspace_id: UUID
    user_id: UUID
    code_to_id: dict[str, UUID] = field(default_factory=dict)
    id_to_code: dict[UUID, str] = field(default_factory=dict)


@dataclass
class CaseModeResult:
    case_id: str
    category: str
    query: str
    mode: str
    ranked: list[str]
    hit5: float
    mrr: float
    ndcg5: float
    exact_top1: float | None
    latency_ms: float


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    cases_path = path or DEFAULT_CASES_PATH
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    return list(payload["cases"])


def _get_or_create_owner(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == EVAL_OWNER_EMAIL))
    if user:
        return user
    user = User(
        email=EVAL_OWNER_EMAIL,
        name="search-ranking-eval",
        password_hash=hash_password("password-ok-1"),
        status=UserStatus.ACTIVE.value,
        system_role=SystemRole.USER.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_or_create_workspace(db: Session, owner: User) -> Workspace:
    ws = db.scalar(
        select(Workspace).where(
            Workspace.name == EVAL_WORKSPACE_NAME,
            Workspace.owner_id == owner.id,
        )
    )
    if ws:
        return ws
    ws = Workspace(
        name=EVAL_WORKSPACE_NAME,
        type=WorkspaceType.TEAM.value,
        owner_id=owner.id,
    )
    db.add(ws)
    db.flush()
    seed_workspace_defaults(db, ws.id)
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    db.commit()
    db.refresh(ws)
    return ws


def _default_stage(db: Session, workspace_id: UUID) -> WorkspaceStage:
    stage = db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == workspace_id,
            WorkspaceStage.is_default.is_(True),
        )
    )
    if stage is None:
        raise RuntimeError("eval workspace missing default stage")
    return stage


def wipe_eval_workspace_ideas(db: Session, workspace_id: UUID) -> None:
    idea_ids = list(db.scalars(select(Idea.id).where(Idea.workspace_id == workspace_id)))
    if not idea_ids:
        return
    db.execute(delete(Notification).where(Notification.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaComment).where(IdeaComment.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaReviewRequest).where(IdeaReviewRequest.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaValidation).where(IdeaValidation.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaParticipant).where(IdeaParticipant.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaShare).where(IdeaShare.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaTag).where(IdeaTag.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaEmbeddingJob).where(IdeaEmbeddingJob.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaEmbedding).where(IdeaEmbedding.idea_id.in_(idea_ids)))
    db.execute(delete(Idea).where(Idea.id.in_(idea_ids)))
    db.commit()


def seed_eval_corpus(db: Session, *, settings: Settings | None = None) -> EvalContext:
    cfg = settings or get_settings()
    owner = _get_or_create_owner(db)
    ws = _get_or_create_workspace(db, owner)
    wipe_eval_workspace_ideas(db, ws.id)
    stage = _default_stage(db, ws.id)
    provider = TopicAwareEvalEmbeddingProvider(cfg)

    code_to_id: dict[str, UUID] = {}
    id_to_code: dict[UUID, str] = {}

    for item in reversed(SEARCH_RANKING_CORPUS):
        payload = IdeaCreate(
            title=item["title"],
            one_line_definition=item.get("one_line_definition"),
            problem=item.get("problem", "eval problem"),
            core_concept=item.get("core_concept", "eval concept"),
            expected_effect=item.get("expected_effect"),
            tags=list(item.get("tags") or []),
            visibility=IdeaVisibility.WORKSPACE,
            stage_id=stage.id,
        )
        idea = idea_service.create_idea(
            db, workspace_id=ws.id, author=owner, payload=payload
        )
        db.flush()
        job = db.get(IdeaEmbeddingJob, idea.id)
        if job is not None:
            db.delete(job)
        tag_names = list(item.get("tags") or [])
        text = build_idea_embedding_text(idea, tag_names)
        vector = provider.embed_text(text)
        db.add(
            IdeaEmbedding(
                idea_id=idea.id,
                workspace_id=ws.id,
                embedding=vector,
                content_hash=compute_content_hash(text),
                model_name=cfg.embedding_model_name,
                dimension=cfg.embedding_dimension,
            )
        )
        code_to_id[item["code"]] = idea.id
        id_to_code[idea.id] = item["code"]
    db.commit()

    bump_codes = [
        "SR-MEET-01",
        "SR-INV-01",
        "SR-MED-WRITE-01",
        "SR-OCR-01",
        "SR-CRM-01",
        "SR-LOG-01",
        "SR-HR-01",
        "SR-AUTO-01",
        "SR-AI-DOC-01",
        "SR-AUTO-02",
        "SR-MED-SEARCH-01",
        "SR-EDU-01",
        "SR-RET-01",
    ]
    base = datetime.now(timezone.utc)
    for i, code in enumerate(bump_codes):
        idea_id = code_to_id.get(code)
        if not idea_id:
            continue
        db.execute(
            update(Idea)
            .where(Idea.id == idea_id)
            .values(updated_at=base + timedelta(seconds=len(bump_codes) - i))
        )
    db.commit()

    return EvalContext(
        workspace_id=ws.id,
        user_id=owner.id,
        code_to_id=code_to_id,
        id_to_code=id_to_code,
    )


def _codes_from_ideas(ideas: list[Idea], id_to_code: dict[UUID, str]) -> list[str]:
    out: list[str] = []
    for idea in ideas:
        code = id_to_code.get(idea.id) or extract_idea_code(idea.title)
        if code:
            out.append(code)
    return out


def run_mode_query(
    db: Session,
    *,
    ctx: EvalContext,
    query: str,
    mode: str,
    top_k: int,
    settings: Settings,
    provider_factory,
    rrf_k: int | None = None,
    candidate_limit: int | None = None,
) -> tuple[list[str], float]:
    started = time.perf_counter()
    if mode == "keyword":
        resp = idea_service.list_ideas(
            db,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            q=query,
            limit=top_k,
            offset=0,
        )
        ordered_ids = [item.id for item in resp.items]
        by_id = {
            idea.id: idea
            for idea in db.scalars(select(Idea).where(Idea.id.in_(ordered_ids))).all()
        }
        ideas = [by_id[i] for i in ordered_ids if i in by_id]
    elif mode == "semantic":
        ideas, _ = idea_search.list_semantic_ideas(
            db,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            q=query,
            limit=top_k,
            offset=0,
            settings=settings,
            provider_factory=provider_factory,
        )
    elif mode == "hybrid":
        ideas, _ = idea_search.list_hybrid_ideas(
            db,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            q=query,
            limit=top_k,
            offset=0,
            settings=settings,
            provider_factory=provider_factory,
            rrf_k=rrf_k,
            candidate_limit=candidate_limit,
        )
    else:
        raise ValueError(f"unknown mode: {mode}")
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return _codes_from_ideas(ideas, ctx.id_to_code), elapsed_ms


def evaluate_cases(
    db: Session,
    *,
    ctx: EvalContext,
    cases: list[dict[str, Any]],
    modes: list[str] | None = None,
    top_k: int = 5,
    settings: Settings | None = None,
    rrf_k: int | None = None,
    candidate_limit: int | None = None,
) -> list[CaseModeResult]:
    cfg = settings or get_settings()
    provider_factory = lambda s: TopicAwareEvalEmbeddingProvider(s)
    modes = modes or ["keyword", "semantic", "hybrid"]
    results: list[CaseModeResult] = []
    for case in cases:
        relevance = {str(k): int(v) for k, v in (case.get("relevance") or {}).items()}
        expected_top = case.get("expected_top_idea")
        for mode in modes:
            ranked, latency_ms = run_mode_query(
                db,
                ctx=ctx,
                query=case["query"],
                mode=mode,
                top_k=top_k,
                settings=cfg,
                provider_factory=provider_factory,
                rrf_k=rrf_k if mode == "hybrid" else None,
                candidate_limit=candidate_limit if mode == "hybrid" else None,
            )
            results.append(
                CaseModeResult(
                    case_id=case["id"],
                    category=case.get("category") or "unknown",
                    query=case["query"],
                    mode=mode,
                    ranked=ranked,
                    hit5=hit_at_k(ranked, relevance, k=top_k),
                    mrr=mrr(ranked, relevance, preferred=expected_top),
                    ndcg5=ndcg_at_k(ranked, relevance, k=top_k),
                    exact_top1=exact_top1(ranked, expected_top),
                    latency_ms=latency_ms,
                )
            )
    return results


def summarize(results: list[CaseModeResult]) -> dict[str, dict[str, float]]:
    by_mode: dict[str, list[CaseModeResult]] = {}
    for row in results:
        by_mode.setdefault(row.mode, []).append(row)
    summary: dict[str, dict[str, float]] = {}
    for mode, rows in by_mode.items():
        exact_vals = [r.exact_top1 for r in rows if r.exact_top1 is not None]
        summary[mode] = {
            "hit@5": mean([r.hit5 for r in rows]),
            "mrr": mean([r.mrr for r in rows]),
            "ndcg@5": mean([r.ndcg5 for r in rows]),
            "exact_top1": mean(exact_vals) if exact_vals else float("nan"),
            "latency_p50_ms": _percentile([r.latency_ms for r in rows], 50),
            "latency_avg_ms": mean([r.latency_ms for r in rows]),
            "n": float(len(rows)),
        }
    return summary


def summarize_by_category(
    results: list[CaseModeResult],
) -> dict[str, dict[str, dict[str, float]]]:
    grouped: dict[str, dict[str, list[CaseModeResult]]] = {}
    for row in results:
        grouped.setdefault(row.category, {}).setdefault(row.mode, []).append(row)
    out: dict[str, dict[str, dict[str, float]]] = {}
    for category, modes in grouped.items():
        out[category] = {}
        for mode, rows in modes.items():
            exact_vals = [r.exact_top1 for r in rows if r.exact_top1 is not None]
            out[category][mode] = {
                "hit@5": mean([r.hit5 for r in rows]),
                "mrr": mean([r.mrr for r in rows]),
                "ndcg@5": mean([r.ndcg5 for r in rows]),
                "exact_top1": mean(exact_vals) if exact_vals else float("nan"),
                "n": float(len(rows)),
            }
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def format_summary_table(summary: dict[str, dict[str, float]]) -> str:
    headers = ("Mode", "Hit@5", "MRR", "nDCG@5", "Exact Top1", "p50 ms")
    lines = [
        f"{headers[0]:<10} {headers[1]:>7} {headers[2]:>7} "
        f"{headers[3]:>8} {headers[4]:>10} {headers[5]:>8}"
    ]
    for mode in ("keyword", "semantic", "hybrid"):
        if mode not in summary:
            continue
        s = summary[mode]
        exact = s["exact_top1"]
        exact_s = f"{exact:.3f}" if exact == exact else "n/a"
        lines.append(
            f"{mode:<10} {s['hit@5']:7.3f} {s['mrr']:7.3f} "
            f"{s['ndcg@5']:8.3f} {exact_s:>10} {s['latency_p50_ms']:8.1f}"
        )
    return "\n".join(lines)
