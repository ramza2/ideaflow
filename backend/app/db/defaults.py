"""Default Workspace Stage / Category definitions.

These are inserted per-workspace when a Workspace is created (Step 4 Service).
Do not seed them as global rows in migrations.
"""

from __future__ import annotations

from typing import TypedDict


class StageDefault(TypedDict):
    sort_order: int
    slug: str
    label: str
    is_default: bool
    is_terminal: bool


class CategoryDefault(TypedDict):
    sort_order: int
    slug: str
    name: str


DEFAULT_WORKSPACE_STAGES: tuple[StageDefault, ...] = (
    {
        "sort_order": 10,
        "slug": "memo",
        "label": "메모",
        "is_default": True,
        "is_terminal": False,
    },
    {
        "sort_order": 20,
        "slug": "organizing",
        "label": "정리 중",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 30,
        "slug": "reviewing",
        "label": "검토 중",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 40,
        "slug": "validation_candidate",
        "label": "검증 후보",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 50,
        "slug": "validating",
        "label": "검증 진행",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 60,
        "slug": "execution_candidate",
        "label": "실행 후보",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 70,
        "slug": "executing",
        "label": "실행 중",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 80,
        "slug": "completed",
        "label": "완료",
        "is_default": False,
        "is_terminal": True,
    },
    {
        "sort_order": 90,
        "slug": "on_hold",
        "label": "보류",
        "is_default": False,
        "is_terminal": False,
    },
    {
        "sort_order": 100,
        "slug": "discarded",
        "label": "폐기",
        "is_default": False,
        "is_terminal": True,
    },
)

DEFAULT_WORKSPACE_CATEGORIES: tuple[CategoryDefault, ...] = (
    {"sort_order": 10, "slug": "product_service", "name": "제품·서비스"},
    {"sort_order": 20, "slug": "technology_rd", "name": "기술·R&D"},
    {"sort_order": 30, "slug": "business_marketing", "name": "사업·마케팅"},
    {"sort_order": 40, "slug": "workflow_improvement", "name": "업무 개선"},
    {"sort_order": 50, "slug": "organization_operation", "name": "조직·운영"},
    {"sort_order": 60, "slug": "content_education", "name": "콘텐츠·교육"},
    {"sort_order": 70, "slug": "lifestyle_personal", "name": "생활·개인"},
    {"sort_order": 80, "slug": "other", "name": "기타"},
)
