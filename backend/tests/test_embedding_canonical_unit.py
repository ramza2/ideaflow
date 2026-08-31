"""Canonical embedding text and hash unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.embeddings.canonical import (
    build_idea_embedding_text,
    compute_content_hash,
    embedding_fields_changed,
    is_embedding_current,
)
from app.core.config import Settings


def _idea(**kwargs):
    defaults = {
        "title": "AI healthcare assistant",
        "one_line_definition": "Clinical decision support",
        "problem": "Doctors lack time",
        "core_concept": "LLM triage",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_same_idea_same_canonical_text_and_hash() -> None:
    idea = _idea()
    text_a = build_idea_embedding_text(idea, ["AI", "healthcare"])
    text_b = build_idea_embedding_text(idea, ["healthcare", "AI"])
    assert text_a == text_b
    assert compute_content_hash(text_a) == compute_content_hash(text_b)


def test_title_change_changes_hash() -> None:
    base = _idea()
    h1 = compute_content_hash(build_idea_embedding_text(base, []))
    h2 = compute_content_hash(build_idea_embedding_text(_idea(title="Different"), []))
    assert h1 != h2


def test_problem_and_tags_change_hash() -> None:
    idea = _idea()
    h1 = compute_content_hash(build_idea_embedding_text(idea, []))
    h2 = compute_content_hash(build_idea_embedding_text(_idea(problem="New problem"), []))
    h3 = compute_content_hash(build_idea_embedding_text(idea, ["new-tag"]))
    assert h1 != h2 != h3


def test_non_content_fields_do_not_change_embedding_fields_set() -> None:
    assert not embedding_fields_changed({"priority"})
    assert not embedding_fields_changed({"assignee_id", "stage_id", "visibility"})
    assert embedding_fields_changed({"title"})
    assert embedding_fields_changed({"tags"})


def test_is_embedding_current_requires_model_and_dimension() -> None:
    settings = Settings(
        _env_file=None,
        EMBEDDING_MODEL_NAME="BAAI/bge-m3",
        EMBEDDING_DIMENSION=1024,
    )
    h = "abc"
    assert is_embedding_current(
        stored_hash=h,
        stored_model="BAAI/bge-m3",
        stored_dimension=1024,
        current_hash=h,
        settings=settings,
    )
    assert not is_embedding_current(
        stored_hash=h,
        stored_model="other-model",
        stored_dimension=1024,
        current_hash=h,
        settings=settings,
    )


def test_truncation_is_deterministic() -> None:
    idea = _idea(title="T", problem="P" * 100)
    settings = Settings(_env_file=None, EMBEDDING_MAX_INPUT_CHARS=20)
    a = build_idea_embedding_text(idea, [], max_chars=settings.embedding_max_input_chars)
    b = build_idea_embedding_text(idea, [], max_chars=settings.embedding_max_input_chars)
    assert a == b
    assert len(a) <= 20
