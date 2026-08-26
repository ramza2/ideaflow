# IdeaFlow Backend

## Current scope (Step 7)

- FastAPI application + health API (Step 1)
- PostgreSQL connection (SQLAlchemy 2.x sync + psycopg 3)
- Alembic migrations + core ORM entities (Step 2)
- Server-side session authentication (Step 3)
- Workspace provisioning + WorkspaceMember RBAC (Step 4)
- Idea CRUD + ACL + ILIKE/FTS search (Step 5)
- Frontend API wiring (Step 6 — frontend package)
- **AI Session + AiJob + OpenAI-compatible LLM provider (Step 7)**
  - `IdeaAiSession` / `AiJob` (PostgreSQL queue)
  - In-process worker (`FOR UPDATE SKIP LOCKED`, lease, retry/backoff)
  - Qwen3-14B via configurable OpenAI-compatible HTTP adapter (`httpx`)
  - Clarification / retry / confirm → existing Idea service (exactly-once)

Frontend AI workflow pages remain **mock** until Step 8. Web Search is Step 9.

## Requirements

- Python 3.11+
- PostgreSQL 16+ (for migrations / integration tests)

## Install

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Configuration

Use repository-root `.env` (or real environment variables). Example:

```text
DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
AUTH_COOKIE_SECURE=false
AI_WORKER_ENABLED=true
LLM_API_URL=https://alzi-llm.openlink.kr
LLM_CHAT_COMPLETIONS_PATH=/v1/chat/completions
LLM_MODEL_NAME=Qwen3-14B
LLM_API_KEY=
```

Environment variables override `.env` values. See root `.env.example` for Auth, LLM, and AI Worker knobs.

**Policy notes**

- `workspace.allow_llm=false` blocks POST session / clarifications / retry (403 `WORKSPACE_LLM_DISABLED`).
- GET session and POST confirm do **not** call the LLM; they remain available even if `allow_llm` is later turned off.
- AI sessions are **requester-only** (Workspace ADMIN / SYSTEM_ADMIN do not bypass).

## Run (dev)

```bash
cd backend
uvicorn app.main:app --reload
```

Health check: `http://127.0.0.1:8000/api/v1/health`

With `AI_WORKER_ENABLED=true`, an in-process daemon thread polls `ai_jobs` and calls the LLM provider. Set `AI_WORKER_ENABLED=false` in tests so the worker does not consume jobs during FastAPI lifespan.

## LLM probe

```bash
cd backend
python -m app.cli.llm_probe
```

Prints provider/model/status/latency without logging API keys, prompts, or raw responses.

## Bootstrap SYSTEM_ADMIN

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
alembic upgrade head
python -m app.cli.create_admin
```

Backfill Personal workspaces:

```bash
python -m app.cli.ensure_personal_workspaces
```

## Migrations

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
alembic upgrade head
alembic current
alembic check
```

Step 7 adds revision `0003_ai_sessions_jobs` (`idea_ai_sessions`, `ai_jobs`).

## Tests

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
export AI_WORKER_ENABLED=false
pytest
```

Optional real LLM integration (not required for CI):

```bash
RUN_LLM_INTEGRATION=1 pytest -k llm_integration
```

## AI Session API (Step 7)

```text
POST   /api/v1/workspaces/{workspace_id}/ai-sessions
GET    /api/v1/workspaces/{workspace_id}/ai-sessions/{session_id}
POST   /api/v1/workspaces/{workspace_id}/ai-sessions/{session_id}/clarifications
POST   /api/v1/workspaces/{workspace_id}/ai-sessions/{session_id}/retry
POST   /api/v1/workspaces/{workspace_id}/ai-sessions/{session_id}/confirm
```
