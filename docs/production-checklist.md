# IdeaFlow Production Checklist

Use before first go-live and after major updates.

## Environment & secrets

- [ ] `.env` created from `deploy/.env.example` (mode `600`)
- [ ] `APP_ENV=production`
- [ ] `POSTGRES_PASSWORD` not a placeholder; matches `DATABASE_URL`
- [ ] `TEST_DATABASE_URL` **not** set in production `.env`
- [ ] Real secrets not committed to git
- [ ] `CORS_ORIGINS` matches the public browser origin (no `*`)
- [ ] HTTPS → `AUTH_COOKIE_SECURE=true`; LAN HTTP → `false` intentionally
- [ ] `AUTH_CSRF_COOKIE_NAME` == `VITE_AUTH_CSRF_COOKIE_NAME`
- [ ] `INTEGRATION_SECRET_ENCRYPTION_KEY` set if Runtime API keys are stored

## Compose / network

- [ ] `IDEAFLOW_DEPLOY_MODE` = `direct` or `traefik`
- [ ] PostgreSQL published only on `127.0.0.1` (or not at all publicly)
- [ ] Backend `8000` not published to the Internet
- [ ] Traefik mode: external network exists; only frontend attached
- [ ] Named volume `ideaflow_pgdata` present
- [ ] `restart: unless-stopped` on db/backend/frontend
- [ ] Log rotation options present on long-running services

## Database

- [ ] `pgvector` extension available
- [ ] `alembic current` == `alembic heads`
- [ ] Backup script succeeds: `./scripts/backup-postgres.sh`
- [ ] Restore verified to fresh `ideaflow_restore_test` (default clean path)
- [ ] Know **not** to run `docker compose down -v` in production
- [ ] Know production restore leaves app stopped until compatible deploy

## Application

- [ ] `./scripts/deploy.sh` completed
- [ ] `GET /healthz` OK
- [ ] `GET /api/v1/health` OK (optional `git_sha`)
- [ ] `GET /api/v1/health/ready` OK
- [ ] Initial `SYSTEM_ADMIN` created
- [ ] Login works
- [ ] Idea list works
- [ ] Keyword search works

## AI / embedding

- [ ] LLM URL reachable (optional probe / Admin diagnostic)
- [ ] Embedding disabled **or** endpoint configured with dim 1024
- [ ] If embedding enabled: coverage checked; semantic/hybrid smoke
- [ ] Semantic unavailable → keyword fallback disclosure still correct
- [ ] Research failure preserves previous READY

## Workers / reboot

- [ ] Backend container healthy with workers enabled as intended
- [ ] `docker compose restart backend` recovers
- [ ] Host reboot → containers auto-start → smoke passes

## Smoke

- [ ] `./scripts/smoke-production.sh`
- [ ] Manual Research history / compare spot-check
- [ ] Confirmed **no** `pytest` against production DB

## Rollback readiness

- [ ] Recent dump exists under `backups/`
- [ ] Operator knows app-only rollback vs backup restore + compatible revision deploy
- [ ] Operator knows migration failure is fail-closed (app stays stopped)

## Mini PC go-live (required before trusting production)

Do **not** force a real production DB overwrite test against live data.

- [ ] Current stack running
- [ ] Run `./scripts/deploy.sh` on an already-up stack
- [ ] Confirm frontend/backend **stop before** migration
- [ ] Confirm migration success then normal backend/frontend start
- [ ] `./scripts/backup-postgres.sh` succeeds
- [ ] Fresh `ideaflow_restore_test` restore succeeds
- [ ] `./scripts/smoke-production.sh` passes
- [ ] Host reboot → containers auto-start
- [ ] Smoke again after reboot
