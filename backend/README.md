# IdeaFlow Backend

## Current scope (Step 3)

- FastAPI application + health API (Step 1)
- PostgreSQL connection (SQLAlchemy 2.x sync + psycopg 3)
- Alembic migrations + core ORM entities (Step 2)
- Server-side session authentication (Step 3)
  - Argon2id password hashing (`pwdlib`)
  - Opaque session cookie + CSRF double-submit
  - Login / logout / me / password change
  - SYSTEM_ADMIN bootstrap CLI

Workspace/Idea APIs, Frontend auth wiring, and LLM features are **not** implemented yet.

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

Self-signup is off. Create the first admin interactively (password via `getpass`, not argv):

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
alembic upgrade head
python -m app.cli.create_admin
```

## Migrations

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
alembic upgrade head
alembic current
alembic downgrade -1
alembic upgrade head
alembic check
```

## Tests

```bash
cd backend
pytest
```

PostgreSQL integration tests (including auth) run when `DATABASE_URL` is set:

```bash
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
pytest
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness / service metadata |
| GET | `/api/v1/auth/csrf` | Issue pre-auth CSRF cookie + token |
| POST | `/api/v1/auth/login` | Login (CSRF required); sets session cookie |
| GET | `/api/v1/auth/me` | Current user from session cookie |
| PATCH | `/api/v1/auth/password` | Change password (CSRF); revokes other sessions |
| POST | `/api/v1/auth/logout` | Logout (CSRF); revokes session |

Session token is never returned in JSON. Cookie: `ideaflow_session` (HttpOnly). CSRF: `ideaflow_csrf` + `X-CSRF-Token`.
