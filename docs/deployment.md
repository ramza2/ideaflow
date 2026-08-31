# IdeaFlow Deployment Guide

## Overview

IdeaFlow can be deployed on a single Linux host with Docker Engine and Docker Compose v2. The stack serves the React SPA through Nginx and proxies API requests to FastAPI on the same Docker network.

```text
Browser
   │
   ▼
Nginx (frontend)
   ├─ /              → React static files
   └─ /api/*         → FastAPI reverse proxy
                           │
                           ▼
                     FastAPI + AI Worker (single process)
                           │
                           ▼
                       PostgreSQL
```

External integrations (OpenAI-compatible LLM, optional Web Search) are reached from the backend container over the network. They are not part of the Docker Compose stack.

## Prerequisites

- Linux host with Docker Engine
- Docker Compose v2 (`docker compose`)
- `curl` on the host (used by `scripts/deploy.sh` for smoke checks)
- Git clone of this repository

Recommended for a home / mini-PC deployment:

- 2+ CPU cores
- 4+ GB RAM
- Persistent disk for the PostgreSQL named volume

## Architecture

| Service | Image / build | Purpose |
|---------|---------------|---------|
| `db` | `postgres:16-alpine` | PostgreSQL database |
| `migrate` | backend image (one-shot) | `alembic upgrade head` |
| `backend` | backend image | FastAPI + in-process AI worker (`--workers 1`) |
| `frontend` | frontend image | Nginx serving built SPA + `/api/` proxy |

Only the frontend publishes a host port (default `8080`). PostgreSQL and the backend API are not exposed on the host.

## Environment setup

1. Copy the deployment example env file to the repository root:

```bash
cp deploy/.env.example .env
```

2. Edit `.env` and set at least:

- `POSTGRES_PASSWORD` — use a long random password (do not keep the placeholder)
- `DATABASE_URL` — password must match `POSTGRES_PASSWORD` (URL-encode special characters if needed); hostname must be `db` inside Docker
- `CORS_ORIGINS` — browser origin users will use (for example `http://192.168.1.50:8080`)
- `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` — if AI features are required
- `WEB_SEARCH_API_URL`, `WEB_SEARCH_API_KEY` — optional; empty is valid (`NOT_CONFIGURED`)

### URL-encoding database passwords

If `POSTGRES_PASSWORD` contains URL reserved characters (`@`, `:`, `/`, `?`, `#`, etc.), encode them in `DATABASE_URL`. Example: password `p@ss:word` becomes `p%40ss%3Aword` in the URL.

### Build-time vs runtime variables

| Variable | When applied | Notes |
|----------|--------------|-------|
| `VITE_API_BASE_URL` | Frontend image build | Production default: `/api/v1` |
| `VITE_AUTH_CSRF_COOKIE_NAME` | Frontend image build | Must match `AUTH_CSRF_COOKIE_NAME` |
| `LLM_*`, `WEB_SEARCH_*`, `AUTH_*` | Backend container startup | Restart/recreate backend after changes |

Changing `VITE_*` values requires rebuilding the frontend image (`./scripts/deploy.sh`).

## deploy.sh usage

The official deployment entry point is:

```bash
./scripts/deploy.sh
```

Options:

```bash
./scripts/deploy.sh --no-build
./scripts/deploy.sh --force-recreate
./scripts/deploy.sh --migrate-only
./scripts/deploy.sh --help
```

| Option | Behavior |
|--------|----------|
| (default) | Build images, start DB, run migration, start app, health checks |
| `--build` | Same as default (explicit rebuild) |
| `--no-build` | Use existing images; DB → migrate → up → health |
| `--force-recreate` | Recreate backend and frontend containers |
| `--migrate-only` | DB healthy → migration → exit (minimal app impact) |

The script uses `set -Eeuo pipefail`, validates `.env` via Docker Compose's resolved environment (not Bash `source .env`), refuses placeholder passwords in both `POSTGRES_PASSWORD` and `DATABASE_URL`, and does not print secrets.

## First deployment

```bash
git clone https://github.com/ramza2/ideaflow.git
cd ideaflow

cp deploy/.env.example .env
# Edit .env — especially POSTGRES_PASSWORD and DATABASE_URL

chmod +x scripts/deploy.sh   # only if executable bit was not preserved
./scripts/deploy.sh
```

Default URL after deployment:

```text
http://<host>:8080
```

## Create initial SYSTEM_ADMIN

After a successful deployment:

```bash
docker compose exec backend python -m app.cli.create_admin
```

This uses the existing interactive CLI. No separate bootstrap API is provided.

## Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /healthz` | Nginx liveness (returns `ok`) |
| `GET /api/v1/health` | API liveness |
| `GET /api/v1/health/ready` | API readiness (PostgreSQL `SELECT 1`; does not call LLM/Web Search) |

Example:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

## Logs

```bash
docker compose logs -f --tail=200 backend
docker compose logs -f --tail=200 frontend
docker compose logs -f --tail=200 db
```

## Restart / stop

Restart application services (does not re-run the one-shot `migrate` service):

```bash
docker compose restart backend frontend
```

Restart the database only when needed:

```bash
docker compose restart db
```

Stop the stack (keeps the database volume):

```bash
docker compose down
```

**Warning:** `docker compose down -v` deletes the `ideaflow_pgdata` volume and all database data. Do not use this in production unless you intend to wipe data.

## Application update

```bash
git pull --ff-only
./scripts/deploy.sh
```

To skip image rebuild when images are already current:

```bash
./scripts/deploy.sh --no-build
```

Take a database backup before production updates (see below).

## Database backup

```bash
mkdir -p backups

docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > backups/ideaflow_$(date +%Y%m%d_%H%M%S).sql
```

The password is not passed on the command line; it is read from the container environment.

## Database restore

Back up the current database before restoring.

```bash
cat backups/ideaflow_backup.sql | \
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## LAN HTTP deployment

Default settings suit a trusted LAN over HTTP:

```text
IDEAFLOW_BIND_ADDRESS=0.0.0.0
IDEAFLOW_HTTP_PORT=8080
AUTH_COOKIE_SECURE=false
CORS_ORIGINS=http://<mini-pc-ip>:8080
```

Access: `http://<mini-pc-ip>:8080`

Do not expose plain HTTP directly to the public Internet. Use HTTPS and a reverse proxy for internet-facing deployments.

## HTTPS reverse proxy deployment

If Nginx, Caddy, or another reverse proxy terminates TLS in front of IdeaFlow:

```text
IDEAFLOW_BIND_ADDRESS=127.0.0.1
IDEAFLOW_HTTP_PORT=8080
AUTH_COOKIE_SECURE=true
CORS_ORIGINS=https://ideas.example.com
```

Public URL: `https://ideas.example.com` → proxy → `http://127.0.0.1:8080`

**Cookie security notes:**

- For HTTPS deployments, set `AUTH_COOKIE_SECURE=true`. Using `false` on HTTPS can still work in some browsers, but cookies are sent without the Secure flag, which increases HTTP downgrade and plaintext exposure risk.
- For HTTP deployments (for example LAN), use `AUTH_COOKIE_SECURE=false`. If set to `true` over plain HTTP, browsers will not send Secure cookies and login/session will not work.

## Environment variable behavior

- **Connection configuration** (LLM URL/key, Web Search URL/key) remains in ENV only (Step 11 principle).
- **Runtime product policy** (`GLOBAL_LLM_ENABLED`, etc.) remains in the database via Admin.
- **CSRF:** `VITE_AUTH_CSRF_COOKIE_NAME` and `AUTH_CSRF_COOKIE_NAME` must match.
- **CORS:** Do not use `CORS_ORIGINS=*` with credential cookies.

## Security notes

- Only port `8080` (or your chosen `IDEAFLOW_HTTP_PORT`) needs to be reachable by browsers.
- Do not publish PostgreSQL (`5432`) or the backend API (`8000`) on the host.
- Never commit `.env` or real secrets to Git.
- Secrets are not copied into Docker images.
- `VITE_*` variables are embedded in the frontend bundle — never pass database or API keys as Vite build args.

## Troubleshooting

### Database unhealthy

```bash
docker compose ps
docker compose logs db
```

Inside Docker, `DATABASE_URL` must use host `db`, not `localhost`.

### DB password mismatch

`POSTGRES_PASSWORD` and the password embedded in `DATABASE_URL` must refer to the same value. `deploy.sh` rejects the placeholder in either field. URL-encode special characters in `DATABASE_URL` when needed (for example `p@ss:word` → `p%40ss%3Aword`). A mismatch prevents backend readiness (`503` on `/api/v1/health/ready`).

### Migration failures

```bash
docker compose logs migrate
docker compose run --rm migrate
```

Do not auto-downgrade or wipe volumes on migration failure. Fix the schema issue or restore from backup.

### Backend / 502 Bad Gateway

```bash
docker compose ps
docker compose logs backend
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

### Auth / session not persisting

Check `AUTH_COOKIE_SECURE` matches your deployment mode (HTTP → `false`, HTTPS → `true`).

### CSRF errors (`CSRF_INVALID`)

Ensure `AUTH_CSRF_COOKIE_NAME` and `VITE_AUTH_CSRF_COOKIE_NAME` are identical, then rebuild the frontend if you changed the Vite value.

### SPA direct URL returns 404

Confirm Nginx `try_files` is configured (`deploy/nginx.conf`). Routes such as `/login`, `/w/{workspaceId}/home`, and `/admin/users` should return `index.html`.

### LLM works in Admin diagnostic but app AI fails

App health can be normal while an external LLM provider is down. Use Admin → Integrations → LLM Diagnostic. Web Search with empty `WEB_SEARCH_API_URL` reports `NOT_CONFIGURED` and does not block startup.

## Pre-merge Docker smoke checklist

Run on a host with Docker Engine before merging deployment changes:

```bash
cp deploy/.env.example .env
# Edit POSTGRES_PASSWORD and DATABASE_URL (and other values as needed)

./scripts/deploy.sh
./scripts/deploy.sh --migrate-only
./scripts/deploy.sh --no-build
```

Verify services:

```bash
docker compose ps
```

Expected:

```text
db       healthy
backend  healthy
frontend healthy
migrate  exited 0 (one-shot; not running during normal deploy)
```

HTTP checks:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -I http://127.0.0.1:8080/login
curl -I http://127.0.0.1:8080/admin/users
```

`/api/nonexistent` must return HTTP 404 from the backend (not React `index.html`).

`deploy.sh` runs migration once per deploy (`docker compose run --rm migrate`) and starts backend/frontend with `--no-deps` so the compose `migrate` dependency is not triggered again. Manual `docker compose up` still enforces `db → migrate → backend → frontend` safety.
