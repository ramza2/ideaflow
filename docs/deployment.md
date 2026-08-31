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

IdeaFlow supports two deployment modes (selected via `IDEAFLOW_DEPLOY_MODE` in `.env`):

### Direct mode (default)

```text
Browser → host:8080 → frontend Nginx → /api → backend → PostgreSQL
```

### Traefik mode

```text
Browser → HTTPS → existing GPU server Traefik → frontend:80 → /api → backend → PostgreSQL
```

Traefik routes **only** the frontend container. Backend, database, and migrate are not attached to the Traefik network.

Compose files:

| File | Purpose |
|------|---------|
| `compose.yaml` | Base services (`db`, `migrate`, `backend`, `frontend`); no host ports |
| `compose.direct.yaml` | Publishes frontend host port for LAN/mini-PC |
| `compose.traefik.yaml` | Traefik labels + external network for GPU server |

`./scripts/deploy.sh` selects the overlay automatically from `IDEAFLOW_DEPLOY_MODE`.

| Service | Image / build | Purpose |
|---------|---------------|---------|
| `db` | `postgres:16-alpine` | PostgreSQL database |
| `migrate` | backend image (one-shot) | `alembic upgrade head` |
| `backend` | backend image | FastAPI + in-process AI worker (`--workers 1`) |
| `frontend` | frontend image | Nginx serving built SPA + `/api/` proxy |

In **direct** mode, only the frontend publishes a host port (default `8080`). In **traefik** mode, no IdeaFlow host ports are published; browsers reach the app through the existing Traefik reverse proxy.

## Environment setup

1. Copy the deployment example env file to the repository root:

```bash
cp deploy/.env.example .env
```

2. Edit `.env` and set at least:

- `IDEAFLOW_DEPLOY_MODE` — `direct` (default) or `traefik`
- `POSTGRES_PASSWORD` — use a long random password (do not keep the placeholder)
- `DATABASE_URL` — password must match `POSTGRES_PASSWORD` (URL-encode special characters if needed); hostname must be `db` inside Docker
- `CORS_ORIGINS` — browser origin users will use
- `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` — if AI features are required
- `WEB_SEARCH_API_URL`, `WEB_SEARCH_API_KEY` — optional; empty is valid (`NOT_CONFIGURED`)

For **traefik** mode, also set `IDEAFLOW_HOST`, `IDEAFLOW_PUBLIC_URL`, `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER`, and `AUTH_COOKIE_SECURE=true`.

### URL-encoding database passwords

If `POSTGRES_PASSWORD` contains URL reserved characters (`@`, `:`, `/`, `?`, `#`, etc.), encode them in `DATABASE_URL`. Example: password `p@ss:word` becomes `p%40ss%3Aword` in the URL.

### Build-time vs runtime variables

| Variable | When applied | Notes |
|----------|--------------|-------|
| `VITE_API_BASE_URL` | Frontend image build | Production default: `/api/v1` |
| `VITE_AUTH_CSRF_COOKIE_NAME` | Frontend image build | Must match `AUTH_CSRF_COOKIE_NAME` |
| `LLM_*`, `WEB_SEARCH_*`, `AUTH_*` | Backend container startup | Restart/recreate backend after changes |

Changing `VITE_*` values requires rebuilding the frontend image (`./scripts/deploy.sh`).

## First deployment

The recommended first-time flow is a single interactive command:

```bash
git clone https://github.com/ramza2/ideaflow.git
cd ideaflow

chmod +x scripts/deploy.sh   # only if executable bit was not preserved
./scripts/deploy.sh
```

If `.env` does not exist and the terminal is interactive, `deploy.sh` runs the **First Deployment Setup Wizard**. It:

1. Prompts for deployment mode (`direct` or `traefik`) and mode-specific settings
2. Generates a secure PostgreSQL password (unless you enter one manually)
3. Derives `DATABASE_URL` automatically from the PostgreSQL settings
4. Writes `.env` atomically with mode `600`
5. Builds images, starts PostgreSQL, runs migrations
6. Creates the initial `SYSTEM_ADMIN` if none exists (interactive prompt)
7. Starts backend and frontend, then runs health smoke checks

First-run Traefik defaults match the OpenLink GPU server pattern (`ideaflow.openlink.kr`, `traefik_proxy`, `websecure`, `letsencrypt`).

### Non-interactive deployment

If `.env` is missing and stdin is not a TTY, deployment fails with instructions to run interactively or copy `deploy/.env.example` manually.

Advanced users may still create `.env` by hand:

```bash
cp deploy/.env.example .env
# edit values, then:
./scripts/deploy.sh
```

## Reconfiguration

To change deployment settings using the wizard with current `.env` values as defaults:

```bash
./scripts/deploy.sh --configure
```

You can update deployment mode, host/public URL, Traefik settings, CORS, and cookie options.

**Database credential rotation is not performed by `--configure`.** Existing `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `DATABASE_URL` are kept unchanged to avoid mismatch with an already-initialized PostgreSQL volume. Coordinated PostgreSQL credential rotation requires a separate operational procedure (not implemented in this PR).

## Interactive setup

The wizard only runs when:

- `.env` is missing (first deployment), or
- `--configure` is passed

Normal redeployments with an existing `.env` skip the wizard.

## Initial administrator

After migrations, `deploy.sh` checks for an **ACTIVE** `SYSTEM_ADMIN` (`deleted_at IS NULL`). If one exists, bootstrap is skipped. If none exists and the terminal is interactive, the existing `create_admin` CLI runs inside a one-off backend container.

Administrator credentials are **not** stored in `.env`.

Manual bootstrap later:

```bash
docker compose -f compose.yaml -f compose.direct.yaml run --rm --no-deps backend python -m app.cli.create_admin
```

Use the Traefik compose overlay instead of `compose.direct.yaml` when in traefik mode.

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
| `--configure` | Interactive reconfiguration using current `.env` as defaults, then deploy |

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

Default URL after **direct** deployment:

```text
http://<host>:8080
```

## Traefik deployment

Use this on a GPU server that already runs Traefik (v3.x with `web` / `websecure` entrypoints and an ACME cert resolver). IdeaFlow attaches only the **frontend** container to the existing Traefik Docker network. Traefik routes HTTP to HTTPS redirect, then HTTPS to frontend port 80. Backend and PostgreSQL stay on the internal `ideaflow` network only.

The label pattern matches existing services on the GPU server (for example `modelflow.openlink.kr`, `alzi.openlink.kr`):

```text
ideaflow-web-http (web) → ideaflow-redirect → HTTPS
ideaflow-web (websecure) → letsencrypt → ideaflow-service:80
```

### Generic example

Replace placeholders with your actual hostname and network:

```text
IDEAFLOW_DEPLOY_MODE=traefik

IDEAFLOW_HOST=<actual-hostname>
IDEAFLOW_PUBLIC_URL=https://<actual-hostname>

TRAEFIK_NETWORK=<existing-traefik-network>
TRAEFIK_ENTRYPOINT=websecure
TRAEFIK_CERTRESOLVER=letsencrypt

AUTH_COOKIE_SECURE=true
CORS_ORIGINS=https://<actual-hostname>
```

### GPU server example (OpenLink)

```text
IDEAFLOW_DEPLOY_MODE=traefik

IDEAFLOW_HOST=ideaflow.openlink.kr
IDEAFLOW_PUBLIC_URL=https://ideaflow.openlink.kr

TRAEFIK_NETWORK=traefik_proxy
TRAEFIK_ENTRYPOINT=websecure
TRAEFIK_CERTRESOLVER=letsencrypt

AUTH_COOKIE_SECURE=true
CORS_ORIGINS=https://ideaflow.openlink.kr
```

`ideaflow.openlink.kr` DNS must point to the GPU server before Traefik can issue a certificate and route traffic.

Deploy:

```bash
./scripts/deploy.sh
```

**Important:**

- `TRAEFIK_NETWORK` must already exist (`docker network inspect <name>`). IdeaFlow does not create or manage Traefik.
- HTTP router uses entrypoint `web`; HTTPS router uses `websecure` with `tls.certresolver` (default `letsencrypt`).
- Do not create a separate Traefik router for `/api` — same-origin Nginx proxies `/api/v1` to the backend.
- `VITE_API_BASE_URL=/api/v1` stays relative; the browser calls `https://<hostname>/api/v1/...`.

Operational commands (traefik mode example):

```bash
docker compose -f compose.yaml -f compose.traefik.yaml ps
docker compose -f compose.yaml -f compose.traefik.yaml logs -f backend
docker compose -f compose.yaml -f compose.traefik.yaml exec backend python -m app.cli.create_admin
```

Direct mode uses `-f compose.yaml -f compose.direct.yaml` instead.

## Create initial SYSTEM_ADMIN

After a successful deployment (use the compose file set matching your `IDEAFLOW_DEPLOY_MODE`):

```bash
# direct mode
docker compose -f compose.yaml -f compose.direct.yaml exec backend python -m app.cli.create_admin

# traefik mode
docker compose -f compose.yaml -f compose.traefik.yaml exec backend python -m app.cli.create_admin
```

Or rely on the compose files hint printed by `./scripts/deploy.sh` at the end of deployment.

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
# direct mode
docker compose -f compose.yaml -f compose.direct.yaml logs -f --tail=200 backend

# traefik mode
docker compose -f compose.yaml -f compose.traefik.yaml logs -f --tail=200 backend
```

## Restart / stop

Restart application services (does not re-run the one-shot `migrate` service):

```bash
docker compose -f compose.yaml -f compose.direct.yaml restart backend frontend
```

Restart the database only when needed:

```bash
docker compose -f compose.yaml -f compose.direct.yaml restart db
```

Use `-f compose.traefik.yaml` instead of `compose.direct.yaml` in traefik mode.

Stop the stack (keeps the database volume):

```bash
docker compose -f compose.yaml -f compose.direct.yaml down
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

## LAN HTTP deployment (direct mode)

Set in `.env`:

```text
IDEAFLOW_DEPLOY_MODE=direct
IDEAFLOW_BIND_ADDRESS=0.0.0.0
IDEAFLOW_HTTP_PORT=8080
AUTH_COOKIE_SECURE=false
CORS_ORIGINS=http://<mini-pc-ip>:8080
```

Access: `http://<mini-pc-ip>:8080`

Do not expose plain HTTP directly to the public Internet.

## HTTPS reverse proxy deployment (external proxy in front of direct mode)

If a separate Nginx/Caddy instance terminates TLS in front of IdeaFlow **direct** mode:

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

- **Direct mode:** only `IDEAFLOW_HTTP_PORT` (default `8080`) needs to be reachable by browsers.
- **Traefik mode:** no IdeaFlow host ports; only the existing Traefik entrypoint is public.
- Do not publish PostgreSQL (`5432`) or the backend API (`8000`) on the host.
- Backend and database are not attached to the Traefik external network.
- Never commit `.env` or real secrets to Git.
- Secrets are not copied into Docker images. No TLS certificates are mounted into IdeaFlow containers.
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

### Direct mode

Run on a host with Docker Engine:

```bash
cp deploy/.env.example .env
# IDEAFLOW_DEPLOY_MODE=direct
# Edit POSTGRES_PASSWORD and DATABASE_URL

./scripts/deploy.sh
./scripts/deploy.sh --migrate-only
./scripts/deploy.sh --no-build
```

```bash
docker compose -f compose.yaml -f compose.direct.yaml ps
```

Expected: `db`, `backend`, `frontend` healthy.

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -I http://127.0.0.1:8080/login
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/nonexistent
```

Expected last command: `404`.

### Traefik mode (GPU server)

```bash
cp deploy/.env.example .env
# IDEAFLOW_DEPLOY_MODE=traefik
# Set IDEAFLOW_HOST, IDEAFLOW_PUBLIC_URL, TRAEFIK_NETWORK,
# TRAEFIK_ENTRYPOINT, TRAEFIK_CERTRESOLVER, AUTH_COOKIE_SECURE=true, CORS_ORIGINS

./scripts/deploy.sh
```

```bash
docker network inspect <TRAEFIK_NETWORK>
docker compose -f compose.yaml -f compose.traefik.yaml ps
```

Expected: `db`, `backend`, `frontend` healthy; frontend attached to Traefik network; backend/db not on Traefik network.

HTTP redirect:

```bash
curl -I http://<IDEAFLOW_HOST>
```

Expected: `301` or `308` with `Location: https://<IDEAFLOW_HOST>/...`

HTTPS and API:

```bash
curl -fsS https://<IDEAFLOW_HOST>/healthz
curl -fsS https://<IDEAFLOW_HOST>/api/v1/health
curl -fsS https://<IDEAFLOW_HOST>/api/v1/health/ready
curl -s -o /dev/null -w '%{http_code}\n' https://<IDEAFLOW_HOST>/api/nonexistent
```

Expected last command: `404`.

Optional certificate inspection:

```bash
openssl s_client -connect <IDEAFLOW_HOST>:443 -servername <IDEAFLOW_HOST>
```

`deploy.sh` runs migration once per deploy (`docker compose run --rm migrate`) and starts backend/frontend with `--no-deps`. Manual `docker compose up` still enforces `db → migrate → backend → frontend` safety.
