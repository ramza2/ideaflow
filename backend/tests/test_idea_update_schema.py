"""Unit tests for IdeaUpdate PATCH validation (no database)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.idea import IdeaUpdate


@pytest.mark.parametrize(
    "payload",
    [
        {"title": None},
        {"stage_id": None},
        {"priority": None},
        {"feasibility": None},
        {"visibility": None},
    ],
)
def test_idea_update_rejects_explicit_null_for_required_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        IdeaUpdate.model_validate(payload)


def test_idea_update_allows_omitted_required_fields() -> None:
    upd = IdeaUpdate.model_validate({"background": "x"})
    assert "title" not in upd.model_fields_set
    assert upd.background == "x"


def test_idea_update_allows_null_clearable_fields() -> None:
    upd = IdeaUpdate.model_validate(
        {
            "category_id": None,
            "assignee_id": None,
            "one_line_definition": None,
            "original_text": None,
            "next_review_date": None,
        }
    )
    assert "category_id" in upd.model_fields_set
    assert upd.category_id is None
