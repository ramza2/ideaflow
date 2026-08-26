# IdeaFlow Backend

## Current scope (Step 4)

- FastAPI application + health API (Step 1)
- PostgreSQL connection (SQLAlchemy 2.x sync + psycopg 3)
- Alembic migrations + core ORM entities (Step 2)
- Server-side session authentication (Step 3)
- Workspace provisioning + WorkspaceMember RBAC (Step 4)
  - Personal workspace ensure / Team workspace create
  - Member add / role / deactivate / reactivate
  - Default Stage (10) + Category (8) per workspace
  - Stage / Category read APIs

Idea CRUD, Frontend auth/workspace wiring, and LLM features are **not** implemented yet.

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

Self-signup is off. Create the first admin interactively (password via `getpass`, not argv).
Creates User + Personal Workspace + owner ADMIN membership + default stages/categories:

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
alembic upgrade head
python -m app.cli.create_admin
```

Backfill Personal workspaces for existing users (no login side effects):

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

Step 4 does not add a new Alembic revision (Step 2 schema is sufficient).

## Tests

```bash
cd backend
pytest
```

PostgreSQL integration tests (auth + workspace) run when `DATABASE_URL` is set:

```bash
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
pytest
```

## Endpoints

### Health / Auth

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness / service metadata |
| GET | `/api/v1/auth/csrf` | Issue pre-auth CSRF cookie + token |
| POST | `/api/v1/auth/login` | Login (CSRF required); sets session cookie |
| GET | `/api/v1/auth/me` | Current user from session cookie |
| PATCH | `/api/v1/auth/password` | Change password (CSRF); revokes other sessions |
| POST | `/api/v1/auth/logout` | Logout (CSRF); revokes session |

### Workspaces (requires auth + password changed)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/workspaces` | List ACTIVE memberships (PERSONAL first) |
| POST | `/api/v1/workspaces` | Create TEAM workspace (CSRF; ADMIN owner) |
| GET | `/api/v1/workspaces/{id}` | Detail (ACTIVE member; else 404) |
| PATCH | `/api/v1/workspaces/{id}` | Update name/flags (ADMIN + CSRF) |
| GET | `/api/v1/workspaces/{id}/members` | Members (ADMIN sees all statuses) |
| POST | `/api/v1/workspaces/{id}/members` | Add/reactivate existing user (ADMIN + CSRF) |
| PATCH | `/api/v1/workspaces/{id}/members/{user_id}` | Change role (ADMIN + CSRF) |
| DELETE | `/api/v1/workspaces/{id}/members/{user_id}` | Deactivate member (ADMIN + CSRF) |
| GET | `/api/v1/workspaces/{id}/stages` | Default stages (read) |
| GET | `/api/v1/workspaces/{id}/categories` | Default categories (read) |

Session token is never returned in JSON. Cookie: `ideaflow_session` (HttpOnly). CSRF: `ideaflow_csrf` + `X-CSRF-Token`.

### RBAC notes

- Access is based on `WorkspaceMember` only — `SYSTEM_ADMIN` does **not** bypass membership.
- PERSONAL workspace membership mutations are blocked (`PERSONAL_WORKSPACE_MEMBERSHIP_IMMUTABLE`).
- Workspace owner role/membership cannot be demoted or removed.
- `must_change_password=true` blocks all Workspace APIs (`403 PASSWORD_CHANGE_REQUIRED`).
