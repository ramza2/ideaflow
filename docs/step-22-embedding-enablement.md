# Step 22 — Embedding enablement & backfill validation

Goal: turn on the existing Idea embedding pipeline, backfill missing vectors via
the existing job worker, and verify Semantic / Hybrid search against real
vectors (not Step 21 fallback).

## Existing pipeline (reuse)

| Item | Value |
|---|---|
| Storage | `idea_embeddings.embedding vector(1024)` + `idea_embedding_jobs` |
| Provider | `openai_compatible` (OpenAI `/v1/embeddings` shape) |
| Default model | `BAAI/bge-m3` (must output **1024** dims) |
| Worker | In-process daemon thread (`EMBEDDING_WORKER_ENABLED`) |
| Enqueue | Idea create / content update; CLI backfill |
| Search | `search_mode=semantic\|hybrid` via pgvector + RRF |

## Enable ENV (no secrets)

```text
EMBEDDING_ENABLED=true
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_API_URL=https://<your-embedding-server>
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_PATH=/v1/embeddings
EMBEDDING_DIMENSION=1024
EMBEDDING_TIMEOUT_SECONDS=30
EMBEDDING_CONNECT_TIMEOUT_SECONDS=5
EMBEDDING_MAX_INPUT_CHARS=20000
EMBEDDING_WORKER_ENABLED=true
EMBEDDING_JOB_POLL_INTERVAL_SECONDS=1
EMBEDDING_JOB_LEASE_SECONDS=120
EMBEDDING_JOB_MAX_ATTEMPTS=3
EMBEDDING_JOB_RETRY_BASE_SECONDS=2
```

Optional: `EMBEDDING_API_KEY` when the endpoint requires Bearer auth.

Runtime Integration Config (`EMBEDDING`) can override the same fields without
restarting the process (worker re-resolves each loop).

## Local smoke without an external endpoint

```bash
pip install sentence-transformers uvicorn fastapi
python scripts/dev_embedding_server.py --host 127.0.0.1 --port 8090
```

Point IdeaFlow at it:

```text
EMBEDDING_ENABLED=true
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_API_URL=http://127.0.0.1:8090
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
```

The helper refuses to start if the loaded model dimension ≠ 1024.

## Coverage / backfill CLI

```bash
# Coverage
python -m app.cli.enqueue_embeddings --coverage
python -m app.cli.enqueue_embeddings --coverage --workspace-id <UUID>

# Dry-run (no writes)
python -m app.cli.enqueue_embeddings --all --dry-run
python -m app.cli.enqueue_embeddings --all --dry-run --limit 50

# Enqueue via existing job pipeline (worker processes async)
python -m app.cli.enqueue_embeddings --all
python -m app.cli.enqueue_embeddings --workspace-id <UUID>
python -m app.cli.enqueue_embeddings --all --limit 100
python -m app.cli.enqueue_embeddings --all --force   # re-embed even if current
```

Idempotency: already-current embeddings (hash + model + dimension) are skipped
unless `--force`. Active QUEUED/RUNNING jobs with the same hash are not
duplicated.

## Dimension rule

Do **not** change `EMBEDDING_DIMENSION` without a new Alembic migration.
Schema is fixed at `vector(1024)`.

## Follow-ups

- Embedding model / version tracking beyond `model_name` on the row
- Automatic periodic reindex
- Ranking (RRF K) tuning
- Admin embedding coverage UI
