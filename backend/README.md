# IdeaFlow Backend

## Current scope (Step 1)

Backend foundation only:

- FastAPI application
- Configuration (`pydantic-settings`)
- `GET /api/v1/health`
- Basic error handling and logging
- pytest setup

Database, Auth, Workspace, Idea, LLM, and related features are **not** implemented yet.

## Requirements

- Python 3.11+

## Install

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Run (dev)

```bash
cd backend
uvicorn app.main:app --reload
```

Health check: `http://127.0.0.1:8000/api/v1/health`

## Tests

```bash
cd backend
pytest
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Liveness / service metadata |
