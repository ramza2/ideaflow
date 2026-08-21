# IdeaFlow Backend

## Current scope (Step 2)

- FastAPI application + health API (Step 1)
- PostgreSQL connection (SQLAlchemy 2.x sync + psycopg 3)
- Alembic migrations
- Core ORM entities (User, Workspace, Idea, …)
- Default Workspace Stage / Category definitions (code constants)

Auth, Workspace/Idea APIs, LLM, and related features are **not** implemented yet.

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
```

Environment variables override `.env` values.

## Run (dev)

```bash
cd backend
uvicorn app.main:app --reload
```

Health check: `http://127.0.0.1:8000/api/v1/health`

## Migrations

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
alembic upgrade head
alembic current
alembic downgrade base   # or: alembic downgrade -1
alembic upgrade head
alembic check
```

## Tests

```bash
cd backend
pytest
```

PostgreSQL integration tests run only when `DATABASE_URL` is set:

```bash
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
pytest
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness / service metadata |
