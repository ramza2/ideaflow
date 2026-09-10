# Step 24 — Dedicated Test DB isolation

## Problem (from Step 23)

Integration fixtures wiped embedding tables on whatever `DATABASE_URL` pointed at
(often the shared/dev `ideaflow` database):

* `tests/test_semantic_search_integration.py` — `TRUNCATE idea_embeddings` / jobs
* `tests/test_idea_research_integration.py` — `DELETE FROM idea_embeddings` / jobs

Symptom: after a local `pytest`, embedding coverage on the app DB fell toward 0%
and required `enqueue_embeddings --all`.

## Target structure

```text
Application / Dev
  DATABASE_URL → ideaflow

Integration pytest
  TEST_DATABASE_URL → ideaflow_test
```

Forbidden:

* `TEST_DATABASE_URL` fallback to `DATABASE_URL`
* Destructive SQL against a non-`*_test` database
* `TEST_DATABASE_URL` resolving to the same host/port/db as `DATABASE_URL`

## Implementation

| Piece | Location |
|---|---|
| Safety helpers | `backend/tests/db_test_safety.py` |
| Embedding wipe (guarded) | `backend/tests/pgvector_helpers.py` |
| Session migrations on test DB | `backend/tests/conftest.py` |
| Unit tests | `backend/tests/test_db_test_safety_unit.py` |
| Developer docs | `docs/testing.md` |
| Env example | `.env.example` |

## Safety checks

1. Database name matches `(^test[_-])|([_-]test$)|([_-]test[_-])`
2. Endpoint ≠ protected `DATABASE_URL` (driver-agnostic host/port/db compare)
3. `assert_test_database_safe` before TRUNCATE/DELETE helpers
4. No `ALLOW_UNSAFE_*` bypass

## Verification checklist

* [ ] No `TEST_DATABASE_URL` → integration skipped; unit pass
* [ ] `TEST_DATABASE_URL=.../ideaflow` → fail-fast before SQL
* [ ] Same DB as `DATABASE_URL` → fail-fast
* [ ] `.../ideaflow_test` → integration pass
* [ ] App DB embedding coverage unchanged across pytest

## Out of scope

Testcontainers, full CI redesign, transaction-rollback fixture rewrite.
