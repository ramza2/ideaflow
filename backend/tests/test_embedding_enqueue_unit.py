"""Unit tests for embedding enqueue scan helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services import embedding_service


def test_scan_ideas_for_enqueue_respects_dry_run_and_limit(monkeypatch) -> None:
    idea_ids = [uuid4() for _ in range(2)]
    ideas = [SimpleNamespace(id=iid) for iid in idea_ids]

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

    db = MagicMock()
    db.scalars.return_value = _Scalars(ideas)
    db.get.return_value = None

    settings = SimpleNamespace(
        embedding_enabled=True,
        embedding_model_name="BAAI/bge-m3",
        embedding_dimension=1024,
        embedding_job_max_attempts=3,
    )

    monkeypatch.setattr(
        embedding_service,
        "compute_idea_content_hash",
        lambda *_a, **_k: "hash",
    )
    calls: list[object] = []

    def _sync(*_a, **_k):
        calls.append(1)
        return True

    monkeypatch.setattr(embedding_service, "sync_embedding_desired_state", _sync)

    scanned, current, queued = embedding_service.scan_ideas_for_enqueue(
        db,
        settings=settings,
        limit=2,
        dry_run=True,
    )
    assert scanned == 2
    assert current == 0
    assert queued == 2
    assert calls == []

    scanned, current, queued = embedding_service.scan_ideas_for_enqueue(
        db,
        settings=settings,
        limit=2,
        dry_run=False,
    )
    assert scanned == 2
    assert queued == 2
    assert len(calls) == 2


def test_scan_ideas_for_enqueue_limit_zero_short_circuits() -> None:
    db = MagicMock()
    settings = SimpleNamespace(embedding_enabled=True)
    scanned, current, queued = embedding_service.scan_ideas_for_enqueue(
        db,
        settings=settings,
        limit=0,
    )
    assert (scanned, current, queued) == (0, 0, 0)
    db.scalars.assert_not_called()
