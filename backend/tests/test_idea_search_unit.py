"""Unit tests for idea search helpers and embedding storage probe."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.services import embedding_service
from app.services.idea_search import (
    HYBRID_MAX_RESULT_WINDOW,
    _validate_hybrid_result_window,
)


def test_validate_hybrid_result_window_allows_supported_range() -> None:
    _validate_hybrid_result_window(0, 50)
    _validate_hybrid_result_window(250, 50)
    _validate_hybrid_result_window(0, HYBRID_MAX_RESULT_WINDOW)


def test_validate_hybrid_result_window_rejects_exceeded_window() -> None:
    with pytest.raises(AppError) as exc_info:
        _validate_hybrid_result_window(300, 1)
    assert exc_info.value.code == "HYBRID_RESULT_WINDOW_EXCEEDED"
    assert exc_info.value.status_code == 400

    with pytest.raises(AppError) as exc_info:
        _validate_hybrid_result_window(250, 51)
    assert exc_info.value.code == "HYBRID_RESULT_WINDOW_EXCEEDED"


class _FakeConnection:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes

    def execute(self, *_args, **_kwargs) -> None:
        if not self._outcomes:
            return
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_args) -> None:
        return None


class _FakeBind:
    def __init__(self) -> None:
        self.connect_calls = 0

    def connect(self) -> _FakeConnection:
        self.connect_calls += 1
        if self.connect_calls == 1:
            return _FakeConnection([RuntimeError("transient db error")])
        return _FakeConnection([])


class _FakeSession:
    def __init__(self) -> None:
        self._bind = _FakeBind()

    def get_bind(self):
        return self._bind


def test_embedding_storage_ready_retries_after_transient_failure() -> None:
    embedding_service._EMBEDDING_STORAGE_READY = None
    db = _FakeSession()

    assert embedding_service.embedding_storage_ready(db) is False
    assert embedding_service._EMBEDDING_STORAGE_READY is None

    assert embedding_service.embedding_storage_ready(db) is True
    assert embedding_service._EMBEDDING_STORAGE_READY is True

    assert embedding_service.embedding_storage_ready(db) is True

    embedding_service._EMBEDDING_STORAGE_READY = None
