"""Unit tests for embedding enqueue scan helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.enums import IdeaEmbeddingJobStatus
from app.services import embedding_service


def _settings(**overrides):
    base = dict(
        embedding_enabled=True,
        embedding_model_name="BAAI/bge-m3",
        embedding_dimension=1024,
        embedding_job_max_attempts=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


def _db_for_ideas(ideas, *, get_map: dict | None = None):
    """MagicMock Session where db.get(Model, id) resolves via get_map[(Model, id)]."""
    db = MagicMock()
    db.scalars.return_value = _Scalars(ideas)
    lookup = get_map or {}

    def _get(model, key):
        return lookup.get((model, key))

    db.get.side_effect = _get
    return db


def test_scan_ideas_for_enqueue_respects_dry_run_and_limit(monkeypatch) -> None:
    idea_ids = [uuid4() for _ in range(2)]
    ideas = [SimpleNamespace(id=iid) for iid in idea_ids]
    db = _db_for_ideas(ideas)

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
        settings=_settings(),
        limit=2,
        dry_run=True,
    )
    assert scanned == 2
    assert current == 0
    assert queued == 2
    assert calls == []

    scanned, current, queued = embedding_service.scan_ideas_for_enqueue(
        db,
        settings=_settings(),
        limit=2,
        dry_run=False,
    )
    assert scanned == 2
    assert queued == 2
    assert len(calls) == 2


def test_scan_ideas_for_enqueue_limit_zero_short_circuits() -> None:
    db = MagicMock()
    scanned, current, queued = embedding_service.scan_ideas_for_enqueue(
        db,
        settings=_settings(),
        limit=0,
    )
    assert (scanned, current, queued) == (0, 0, 0)
    db.scalars.assert_not_called()


def test_should_enqueue_helper_matches_sync_rules() -> None:
    assert embedding_service._should_enqueue_or_reset_job(
        force=False,
        content_hash="h",
        had_embedding=False,
        job=None,
        embedding_enabled=True,
    )
    assert not embedding_service._should_enqueue_or_reset_job(
        force=False,
        content_hash="h",
        had_embedding=False,
        job=SimpleNamespace(content_hash="h", status=IdeaEmbeddingJobStatus.QUEUED.value),
        embedding_enabled=True,
    )
    assert not embedding_service._should_enqueue_or_reset_job(
        force=False,
        content_hash="h",
        had_embedding=False,
        job=SimpleNamespace(content_hash="h", status=IdeaEmbeddingJobStatus.RUNNING.value),
        embedding_enabled=True,
    )
    assert embedding_service._should_enqueue_or_reset_job(
        force=False,
        content_hash="h",
        had_embedding=False,
        job=SimpleNamespace(content_hash="h", status=IdeaEmbeddingJobStatus.FAILED.value),
        embedding_enabled=True,
    )
    assert embedding_service._should_enqueue_or_reset_job(
        force=True,
        content_hash="h",
        had_embedding=False,
        job=SimpleNamespace(content_hash="h", status=IdeaEmbeddingJobStatus.QUEUED.value),
        embedding_enabled=True,
    )


def test_dry_run_and_actual_agree_missing_embedding_no_job(monkeypatch) -> None:
    idea = SimpleNamespace(id=uuid4())
    db = _db_for_ideas([idea])
    monkeypatch.setattr(embedding_service, "compute_idea_content_hash", lambda *_a, **_k: "h1")
    sync_calls: list[bool] = []

    def _sync(*_a, **_k):
        sync_calls.append(True)
        return True

    monkeypatch.setattr(embedding_service, "sync_embedding_desired_state", _sync)

    dry = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=True)
    actual = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=False)
    assert dry == (1, 0, 1)
    assert actual == (1, 0, 1)
    assert len(sync_calls) == 1


def test_dry_run_current_embedding_is_already_current(monkeypatch) -> None:
    idea = SimpleNamespace(id=uuid4())
    emb = SimpleNamespace(
        content_hash="h1",
        model_name="BAAI/bge-m3",
        dimension=1024,
    )
    db = _db_for_ideas(
        [idea],
        get_map={(embedding_service.IdeaEmbedding, idea.id): emb},
    )
    monkeypatch.setattr(embedding_service, "compute_idea_content_hash", lambda *_a, **_k: "h1")
    monkeypatch.setattr(
        embedding_service,
        "sync_embedding_desired_state",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("sync should not run")),
    )

    dry = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=True)
    actual = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=False)
    assert dry == (1, 1, 0)
    assert actual == (1, 1, 0)


def test_dry_run_and_actual_agree_active_same_hash_job(monkeypatch) -> None:
    idea = SimpleNamespace(id=uuid4())
    for status in (
        IdeaEmbeddingJobStatus.QUEUED.value,
        IdeaEmbeddingJobStatus.RUNNING.value,
    ):
        job = SimpleNamespace(content_hash="h1", status=status)
        db = _db_for_ideas(
            [idea],
            get_map={(embedding_service.IdeaEmbeddingJob, idea.id): job},
        )
        monkeypatch.setattr(embedding_service, "compute_idea_content_hash", lambda *_a, **_k: "h1")
        sync_calls: list[object] = []

        def _sync(*_a, **_k):
            sync_calls.append(1)
            return False

        monkeypatch.setattr(embedding_service, "sync_embedding_desired_state", _sync)

        dry = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=True)
        actual = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=False)
        assert dry == (1, 0, 0), status
        assert actual == (1, 0, 0), status
        assert len(sync_calls) == 1


def test_dry_run_failed_job_counts_as_queued(monkeypatch) -> None:
    idea = SimpleNamespace(id=uuid4())
    job = SimpleNamespace(
        content_hash="h1",
        status=IdeaEmbeddingJobStatus.FAILED.value,
    )
    db = _db_for_ideas(
        [idea],
        get_map={(embedding_service.IdeaEmbeddingJob, idea.id): job},
    )
    monkeypatch.setattr(embedding_service, "compute_idea_content_hash", lambda *_a, **_k: "h1")
    monkeypatch.setattr(embedding_service, "sync_embedding_desired_state", lambda *_a, **_k: True)

    dry = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=True)
    actual = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=False)
    assert dry == (1, 0, 1)
    assert actual == (1, 0, 1)


def test_dry_run_and_actual_agree_on_force_with_active_job(monkeypatch) -> None:
    idea = SimpleNamespace(id=uuid4())
    job = SimpleNamespace(
        content_hash="h1",
        status=IdeaEmbeddingJobStatus.QUEUED.value,
    )
    emb = SimpleNamespace(
        content_hash="h1",
        model_name="BAAI/bge-m3",
        dimension=1024,
    )
    db = _db_for_ideas(
        [idea],
        get_map={
            (embedding_service.IdeaEmbedding, idea.id): emb,
            (embedding_service.IdeaEmbeddingJob, idea.id): job,
        },
    )
    monkeypatch.setattr(embedding_service, "compute_idea_content_hash", lambda *_a, **_k: "h1")
    monkeypatch.setattr(embedding_service, "sync_embedding_desired_state", lambda *_a, **_k: True)

    # Without force: current embedding → already_current
    dry = embedding_service.scan_ideas_for_enqueue(db, settings=_settings(), dry_run=True)
    assert dry == (1, 1, 0)

    # With force: re-enqueue even though embedding/job look current
    dry_f = embedding_service.scan_ideas_for_enqueue(
        db, settings=_settings(), dry_run=True, force=True
    )
    actual_f = embedding_service.scan_ideas_for_enqueue(
        db, settings=_settings(), dry_run=False, force=True
    )
    assert dry_f == (1, 0, 1)
    assert actual_f == (1, 0, 1)
