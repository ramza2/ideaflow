# IdeaFlow Production Operations

Companion to [`production-deployment.md`](./production-deployment.md).

## Health / readiness

| Probe | Endpoint | Meaning |
|---|---|---|
| Frontend liveness | `GET /healthz` | Nginx up |
| API liveness | `GET /api/v1/health` | Process up (`status/version/env`, optional `git_sha`) |
| API readiness | `GET /api/v1/health/ready` | PostgreSQL `SELECT 1` only |

Remote LLM / Embedding outages must **not** mark readiness unhealthy.
Keyword search, Idea CRUD, and existing Research reads remain available.

Compose healthchecks use readiness for backend and `/healthz` for frontend.

## Database backup

```bash
./scripts/backup-postgres.sh
# optional retention prune (only deletes ideaflow_*.dump under ./backups/)
./scripts/backup-postgres.sh --prune --keep-days 7
```

- Format: `pg_dump -Fc` → `backups/ideaflow_YYYYMMDD_HHMMSS.dump`
- Password stays inside the `db` container env (not on the host CLI)
- `backups/` is gitignored

Suggested MVP retention: keep ~7 daily dumps on the Mini PC disk. Off-host copy
is a Future TODO.

## Restore

Safe verification (default — separate DB, **fresh drop/create** each run):

```bash
./scripts/restore-postgres.sh --dump backups/ideaflow_YYYYMMDD_HHMMSS.dump
# restores into ideaflow_restore_test
```

Production overwrite (dangerous):

```bash
./scripts/backup-postgres.sh   # safety net of current state
./scripts/restore-postgres.sh --dump backups/...dump \
  --target-db ideaflow --confirm-production
# Stops frontend/backend first; leaves them stopped after restore
# Then deploy a dump-compatible app revision — do not merely restart
git checkout <compatible-revision>
./scripts/deploy.sh
./scripts/smoke-production.sh
```

`pg_restore` uses `--clean --if-exists --exit-on-error --single-transaction`.
System DBs (`postgres`, `template0`, `template1`) are rejected. Invalid DB names
are rejected.

## Workers

| Worker | Where | Restart behavior |
|---|---|---|
| AI Worker | Backend process thread | Lease reclaim for expired RUNNING jobs; graceful `stop()` on SIGTERM |
| Embedding Worker | Backend process thread | Same lease/retry pattern; idle when `EMBEDDING_ENABLED=false` |

Operational notes:

- `uvicorn --workers 1` is required so a single process owns the queues.
- Deploy/migrate **stops** backend (and therefore workers) before schema changes.
- Worker down ≠ web down during normal ops: list/search/history still work; AI tasks show failure /
  stalled states via existing Global AI Task UX.
- Research LLM/search failure converges to `FAILED` and preserves previous READY
  (Step 18/20/26 behavior).

## Logs

```bash
docker compose -f compose.yaml -f compose.direct.yaml logs -f --tail=200 backend
docker compose -f compose.yaml -f compose.direct.yaml logs -f --tail=200 db
```

Compose services use `json-file` rotation (`max-size=10m`, `max-file=5`).

Do not log cookies, Authorization headers, or API keys.

## Disk

Watch:

```bash
df -h
docker system df
du -sh backups/ 2>/dev/null || true
docker volume ls | grep ideaflow
```

## Smoke

```bash
./scripts/smoke-production.sh
./scripts/smoke-production.sh --check-embedding
./scripts/smoke-production.sh --check-coverage
```

Read-only by default. Manual UI checks: login, Idea list, keyword/semantic/hybrid,
Research history/compare.

**Never run `pytest` against production `DATABASE_URL`.** Integration tests require
dedicated `TEST_DATABASE_URL` (Step 24 guards).

## Failure scenarios

### PostgreSQL down

- Symptom: `/api/v1/health/ready` → 503; UI API errors
- Check: `docker compose ... ps db` / `logs db` / `pg_isready` health
- Recover: fix volume/disk, `restart db`, wait healthy, restart backend if needed

### Backend down

- Symptom: Nginx `/api` 502; `/healthz` may still be ok
- Check: `logs backend`, container health
- Recover: `restart backend` or `./scripts/deploy.sh --no-build`

### Worker stuck / crash

- Symptom: AI tasks stuck RUNNING then lease expiry requeues/fails
- Check: backend logs for `lease` / job ids
- Recover: restart backend (threads restart); inspect job rows if needed

### LLM endpoint down

- Symptom: create/refine/research AI features fail with clear errors
- Core CRUD + keyword search continue
- Recover: restore remote LLM; retry failed jobs from UI where supported

### Embedding endpoint down

- Symptom: semantic/hybrid unavailable → keyword fallback + disclosure (Step 21)
- Recover: restore embedding API; run coverage / enqueue if jobs piled up

### Disk full

- Symptom: DB write failures, container restarts, backup failures
- Recover: prune old dumps (`backup-postgres.sh --prune`), `docker image prune` carefully,
  free logs; never `down -v`

### Migration failure

- Symptom: `migrate` exits non-zero; **frontend/backend remain stopped** (fail-closed)
- Recover: inspect migrate logs / DB; restore pre-update backup if needed; fix
  migration; redeploy compatible revision with `./scripts/deploy.sh` (not a blind
  container restart). `--migrate-only` also leaves the app stopped until a full deploy.

## Embedding coverage (ops)

```bash
docker compose -f compose.yaml -f compose.direct.yaml exec backend \
  python -m app.cli.enqueue_embeddings --coverage
```

Model/runtime must stay `BAAI/bge-m3` / dimension **1024**.

## Future operations TODO

- Off-host / NAS / object-storage backups
- Prometheus/Grafana, Sentry, Slack alerts
- Blue/green or canary releases
- HA PostgreSQL
