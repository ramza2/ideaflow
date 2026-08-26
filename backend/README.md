# IdeaFlow Backend

## Current scope (Step 5)

- FastAPI application + health API (Step 1)
- PostgreSQL connection (SQLAlchemy 2.x sync + psycopg 3)
- Alembic migrations + core ORM entities (Step 2)
- Server-side session authentication (Step 3)
- Workspace provisioning + WorkspaceMember RBAC (Step 4)
- Idea CRUD + ACL + ILIKE/FTS search (Step 5)
  - PRIVATE / WORKSPACE / SELECTED_USERS
  - IdeaShare READ/EDIT
  - Workspace-scoped `IF-NNN` idea codes (advisory lock)
  - Tags, filters, pagination

Frontend API wiring and LLM features are **not** implemented yet.

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
```

Environment variables override `.env` values. See root `.env.example` for auth-related knobs
(`AUTH_SESSION_*`, `AUTH_CSRF_*`, `AUTH_LOGIN_*`, cookie flags).

## Run (dev)

```bash
cd backend
uvicorn app.main:app --reload
```

Health check: `http://127.0.0.1:8000/api/v1/health`

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

Step 5 does not add a new Alembic revision.

## Tests

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
pytest
```

## Idea Endpoints

Prefix: `/api/v1/workspaces/{workspace_id}/ideas`

Requires ACTIVE WorkspaceMember + `must_change_password=false`. Mutations require CSRF.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/ideas` | List/search (`q`, filters, `limit`/`offset`); ACL in SQL |
| POST | `/ideas` | Create (author = current user); default PRIVATE / memo stage |
| GET | `/ideas/{idea_id}` | Detail; unauthorized → `404 IDEA_NOT_FOUND` |
| PATCH | `/ideas/{idea_id}` | Author or EDIT share (visibility owner-only) |
| DELETE | `/ideas/{idea_id}` | Soft delete; author only |
| GET | `/ideas/{idea_id}/shares` | Author only |
| PUT | `/ideas/{idea_id}/shares` | Full replace; author only |

### ACL (summary)

- **PRIVATE**: author only (no Workspace ADMIN / SYSTEM_ADMIN bypass)
- **WORKSPACE**: ACTIVE members read; author only edit/delete
- **SELECTED_USERS**: author + IdeaShare READ/EDIT read; EDIT may edit content; author only delete/shares/visibility

Leaving SELECTED_USERS clears IdeaShare rows (no stale ACL on re-entry).
