"""Idea structuring prompt v1."""

from __future__ import annotations

import json
from typing import Any

from app.llm.schemas import CategoryOption, IdeaStructuringRequest

IDEA_STRUCTURE_PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """당신은 IdeaFlow의 아이디어 구조화 도우미입니다.

규칙:
1. 사용자의 아이디어를 구조화한다.
2. 사용자가 말하지 않은 외부 사실을 만들어내지 않는다.
3. 시장규모, 통계, 경쟁사, 법규 등 외부 검증이 필요한 사실을 임의 생성하지 않는다.
4. 정보가 없으면 null을 사용한다.
5. 구조화 자체가 어려울 때만 clarification을 요청한다. 모든 빈 필드에 질문하지 않는다.
6. 질문은 최대 3개. 이미 답변된 내용을 다시 질문하지 말 것.
7. 사용자 입력의 주요 언어로 결과를 작성한다.
8. JSON만 반환한다. Markdown 금지.
9. WEB_EVIDENCE provenance를 사용하지 않는다. (Web Search 미사용)
10. workspace_id, author_id, idea_code, stage_id, assignee_id, visibility, shares는 반환하지 않는다.
11. category는 제공된 slug 목록 중 하나만 category_slug로 고른다. 모르면 null.
12. research_recommended / research_topics는 "검색하면 도움될 주제"일 뿐 사실이 아니다. topics는 최대 5개.

decision은 READY_FOR_REVIEW 또는 NEEDS_CLARIFICATION 만 허용한다.

응답 JSON 스키마:
{
  "decision": "READY_FOR_REVIEW" | "NEEDS_CLARIFICATION",
  "draft": {
    "title": string|null,
    "one_line_definition": string|null,
    "background": string|null,
    "problem": string|null,
    "core_concept": string|null,
    "major_features": string|null,
    "expected_effect": string|null,
    "target_users": string|null,
    "scenarios": string|null,
    "challenges": string|null,
    "minimum_validation": string|null,
    "related_project": string|null,
    "category_slug": string|null,
    "priority": "HIGH"|"MEDIUM"|"LOW"|null,
    "feasibility": "HIGH"|"MEDIUM"|"LOW"|"UNKNOWN"|null,
    "tags": string[]
  },
  "field_provenance": {
    "<field>": {"source": "USER_INPUT"|"LLM_SUMMARY"|"LLM_INFERENCE"|"USER_EDIT", "note": string|null}
  },
  "clarifying_questions": [{"field": string|null, "question": string}],
  "research_recommended": boolean,
  "research_topics": string[]
}
"""


def build_user_prompt(request: IdeaStructuringRequest) -> str:
    categories_lines = "\n".join(
        f"- {c.slug} — {c.name}" for c in request.categories
    ) or "- (no categories)"

    parts: list[str] = [
        "다음 사용자 입력을 구조화하세요.",
        "",
        "## 사용 가능한 카테고리 (slug — name)",
        categories_lines,
        "",
        "## 사용자 입력",
        request.input_text,
    ]

    if request.prior_draft is not None:
        parts.extend(
            [
                "",
                "## 이전 draft (검증된 structured data)",
                json.dumps(request.prior_draft, ensure_ascii=False),
            ]
        )

    if request.clarifying_questions:
        parts.extend(
            [
                "",
                "## 이전 질문",
                json.dumps(request.clarifying_questions, ensure_ascii=False),
            ]
        )

    if request.clarification_answers:
        parts.extend(
            [
                "",
                "## 사용자 답변",
                json.dumps(request.clarification_answers, ensure_ascii=False),
                "",
                "이미 답변된 내용을 다시 질문하지 마세요.",
            ]
        )

    parts.extend(["", "JSON만 출력하세요."])
    return "\n".join(parts)


def categories_from_rows(rows: list[Any]) -> list[CategoryOption]:
    return [CategoryOption(slug=r.slug, name=r.name) for r in rows]
