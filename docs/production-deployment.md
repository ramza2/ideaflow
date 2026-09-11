# IdeaFlow Production Deployment

This document is the Step 29 production entrypoint. Detailed Compose/Traefik
mechanics also live in [`deployment.md`](./deployment.md).

## Architecture (current repository)

```text
Home Mini PC / GPU host
├─ frontend          Nginx SPA + /api proxy
├─ backend           FastAPI + in-process AI Worker + Embedding Worker
├─ migrate           one-shot alembic upgrade head
├─ db                PostgreSQL 16 + pgvector (named volume ideaflow_pgdata)
└─ reverse proxy
   ├─ direct mode: host port → frontend
   └─ traefik mode: existing Traefik → frontend only

Remote AI (outside Compose)
├─ LLM OpenAI-compatible endpoint
└─ Embedding OpenAI-compatible endpoint
```

There are **no** separate Docker services for AI/Embedding workers. They run as
daemon threads inside the single uvicorn worker (`--workers 1`).

## Environment template

```bash
cp deploy/.env.example .env
# edit secrets / CORS / LLM / Embedding
```

| Category | Notes |
|---|---|
| Required | `POSTGRES_PASSWORD`, matching `DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV=production` |
| Secrets | DB password, `LLM_API_KEY`, `EMBEDDING_API_KEY`, `WEB_SEARCH_API_KEY`, `INTEGRATION_SECRET_ENCRYPTION_KEY` — placeholders only in git |
| Do not set | `TEST_DATABASE_URL` in production `.env` |
| HTTPS | `AUTH_COOKIE_SECURE=true`, Traefik or external TLS |
| LAN HTTP | `AUTH_COOKIE_SECURE=false` only on trusted network |

## First deployment

```bash
git clone https://github.com/ramza2/ideaflow.git
cd ideaflow
chmod +x scripts/deploy.sh scripts/backup-postgres.sh scripts/restore-postgres.sh scripts/smoke-production.sh
./scripts/deploy.sh
```

Wizard creates `.env` (mode 600), builds images, starts DB, quiesces app (no-op if
absent), migrates, bootstraps `SYSTEM_ADMIN` (interactive), starts app, smoke-checks health.

Manual path: `cp deploy/.env.example .env` → edit → `./scripts/deploy.sh`.

## Regular update

Short maintenance downtime is expected (web + workers stop during migration).

```text
backup
→ git pull
→ ./scripts/deploy.sh
   → build (default)
   → db healthy
   → frontend/backend stop
   → migration
   → admin bootstrap (if needed)
   → backend start
   → frontend start
→ ./scripts/smoke-production.sh
```

```bash
./scripts/backup-postgres.sh
git pull --ff-only
./scripts/deploy.sh
./scripts/smoke-production.sh
```

If migration fails, **fail-closed**: frontend/backend stay stopped. Do not treat the
new app version as live. Inspect migrate logs / DB, then restore or fix and redeploy.

`--migrate-only` also quiesces frontend/backend before migrating and **may exit with
backend/frontend still stopped**. Start the app later with a full `./scripts/deploy.sh`.

Check migration state (when backend is running):

```bash
docker compose -f compose.yaml -f compose.direct.yaml exec backend alembic current
docker compose -f compose.yaml -f compose.direct.yaml exec backend alembic heads
```

## Rollback

**App-only regression (no schema change):** redeploy previous git revision /
images (deploy will quiesce → migrate no-op or compatible → start app).

**Schema / data migration problem:** do **not** assume `alembic downgrade` is
safe. Prefer:

```text
current-state backup (if still possible)
→ app traffic stop (restore script does this for production target)
→ restore pre-update DB dump into production (--confirm-production)
→ checkout previous compatible app revision
→ ./scripts/deploy.sh
→ smoke
```

```bash
./scripts/backup-postgres.sh   # current state before restore, if still possible
./scripts/restore-postgres.sh --dump backups/ideaflow_YYYYMMDD_HHMMSS.dump \
  --target-db ideaflow --confirm-production
# Application remains stopped — do not simply restart old containers
git checkout <previous-compatible-revision>
./scripts/deploy.sh
./scripts/smoke-production.sh
```

Validate backups on `ideaflow_restore_test` first (default restore target; fresh
drop/create each run).

## Host reboot

Services use `restart: unless-stopped`. After Mini PC reboot, Docker should
bring `db` / `backend` / `frontend` back. Verify:

```bash
docker compose -f compose.yaml -f compose.direct.yaml ps
./scripts/smoke-production.sh
```

**Never** use `docker compose down -v` in production (deletes `ideaflow_pgdata`).

## Frontend production build

- `npm run build` inside the frontend image (Vite). Default production builds do **not** emit public source maps.
- `VITE_*` values are bake-time; changing them requires image rebuild.

## Version identity

- `APP_VERSION` (settings)
- Optional `BUILD_GIT_SHA` (set by `deploy.sh` when git is available) exposed on
  `GET /api/v1/health` as `git_sha`

## Related docs

- [`production-operations.md`](./production-operations.md) — backup, workers, failures
- [`production-checklist.md`](./production-checklist.md) — go-live checklist
- [`deployment.md`](./deployment.md) — Compose modes / Traefik / troubleshooting
- [`testing.md`](./testing.md) / [`step-24-test-db-isolation.md`](./step-24-test-db-isolation.md) — never pytest on prod DB
