# Testing

## Unit vs integration

| Kind | When it runs | Database |
|---|---|---|
| Unit | Always (no DB required) | none |
| Integration | Only when `TEST_DATABASE_URL` is set | **dedicated** test DB |

Application runtime always uses `DATABASE_URL` (e.g. `ideaflow`).

Integration pytest always uses `TEST_DATABASE_URL` (e.g. `ideaflow_test`).

There is **no fallback** from `TEST_DATABASE_URL` → `DATABASE_URL`. That pattern
previously allowed shared/dev DB wipes via `TRUNCATE` / `DELETE`.

## Recommended local databases

```text
Dev / app:   ideaflow
Test:        ideaflow_test
```

Both can live in the same PostgreSQL instance (Compose `db` service).

## Create the test database

Same Postgres instance as development (Compose `db` service publishes
`${POSTGRES_PORT:-5432}:5432` for host-side pytest):

```bash
# Docker Compose
docker compose exec db \
  psql -U ideaflow -d ideaflow \
  -c "CREATE DATABASE ideaflow_test OWNER ideaflow;"

# Or local Postgres
createdb -U ideaflow ideaflow_test
```

Do **not** clone production data into the test DB.

## pgvector + migrations

On first integration run, `tests/conftest.py` (session fixture):

1. Validates `TEST_DATABASE_URL` (name marker + not same as `DATABASE_URL`)
2. `CREATE EXTENSION IF NOT EXISTS vector`
3. `alembic upgrade head` against **test** DB only

Manual equivalent:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow_test
cd backend
psql "$TEST_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
alembic -x sqlalchemy.url="$TEST_DATABASE_URL" upgrade head
# or: sqlalchemy.url in alembic.ini temporarily / ALEMBIC config override
```

## Configure `.env`

```env
DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
TEST_DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow_test
```

See root `.env.example`. Never commit real secrets.

## Running tests

```bash
cd backend

# Unit only (works without TEST_DATABASE_URL)
pytest tests/test_refine_schema_unit.py tests/test_db_test_safety_unit.py -q

# Integration (requires TEST_DATABASE_URL)
pytest tests/test_semantic_search_integration.py -q
pytest tests/test_idea_research_integration.py -q
```

If `TEST_DATABASE_URL` is unset, DB integration tests are **skipped** with an
explicit reason. Unit tests still pass.

## Safety guards

Module: `backend/tests/db_test_safety.py`

Before any destructive SQL (`TRUNCATE` / bulk `DELETE`), fixtures call
`assert_test_database_safe(...)`.

Checks:

1. **Name marker** — database name must match
   `(^test[_-])|([_-]test$)|([_-]test[_-])`
   (accepts `ideaflow_test`, `test_ideaflow`, `ideaflow-test-ci`;
   rejects `ideaflow`, `contest`, `latest`).
2. **Same-DB detection** — compares host/port/database with protected
   `DATABASE_URL` (driver/user/password differences ignored).
3. **Fail-fast** — raises `UnsafeTestDatabaseError` (not a warning).

There is **no** `ALLOW_UNSAFE_TEST_DB` override.

## What wiped shared DB before (Step 23)

These fixtures used `DATABASE_URL` and cleared embedding tables:

* `tests/test_semantic_search_integration.py` → `wipe_embedding_tables` / `TRUNCATE`
* `tests/test_idea_research_integration.py` → `DELETE FROM idea_embeddings` / jobs

They now require `TEST_DATABASE_URL` and call the safety guard first.

## Coverage CLI

`python -m app.cli.enqueue_embeddings --coverage` / `--all` continue to use
**`DATABASE_URL`** (application DB). Do not point operational CLIs at the test DB
unless you intentionally want to manage test data.

## CI note

If CI is added later, provision Postgres with `POSTGRES_DB=ideaflow_test` (or
create both DBs) and set `TEST_DATABASE_URL` explicitly. Full CI wiring is out of
scope for Step 24.
