#!/usr/bin/env bash
# Read-only production smoke checks (does not create/modify Idea data).
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# shellcheck source=lib/compose-mode.sh
source "${SCRIPT_DIR}/lib/compose-mode.sh"

BASE_URL=""
CHECK_EMBEDDING=0
CHECK_COVERAGE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/smoke-production.sh [--base-url URL] [--check-embedding] [--check-coverage]

Default base URL:
  direct  → http://127.0.0.1:${IDEAFLOW_HTTP_PORT:-8080}
  traefik → ${IDEAFLOW_PUBLIC_URL}

Checks (read-only):
  GET /healthz
  GET /api/v1/health
  GET /api/v1/health/ready

Optional:
  --check-embedding   Print embedding ENV flags via backend container (no inference)
  --check-coverage    Run embedding coverage CLI (read-only)
EOF
}

log() { printf '%s\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:-}"
      shift
      ;;
    --check-embedding) CHECK_EMBEDDING=1 ;;
    --check-coverage) CHECK_COVERAGE=1 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "Unknown option: $1" ;;
  esac
  shift
done

command -v curl >/dev/null 2>&1 || fail "curl is required"
[[ -f .env ]] || fail ".env not found"

COMPOSE_ARGS="$(compose_cmd_args)"
MODE="$(compose_mode_resolve)"

if [[ -z "${BASE_URL}" ]]; then
  if [[ "${MODE}" == "traefik" ]]; then
    BASE_URL="$(grep -E '^[[:space:]]*IDEAFLOW_PUBLIC_URL=' .env | tail -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    [[ -n "${BASE_URL}" ]] || fail "IDEAFLOW_PUBLIC_URL is required for traefik smoke"
  else
    port="$(grep -E '^[[:space:]]*IDEAFLOW_HTTP_PORT=' .env | tail -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
    port="${port:-8080}"
    BASE_URL="http://127.0.0.1:${port}"
  fi
fi

BASE_URL="${BASE_URL%/}"

wait_ok() {
  local url="$1"
  local name="$2"
  local i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 5 "${url}" >/tmp/ideaflow_smoke_body.txt 2>/dev/null; then
      log "OK  ${name}: ${url}"
      return 0
    fi
    sleep 2
  done
  fail "Failed ${name}: ${url}"
}

log "Smoke base URL: ${BASE_URL}"
wait_ok "${BASE_URL}/healthz" "frontend healthz"
wait_ok "${BASE_URL}/api/v1/health" "api liveness"
wait_ok "${BASE_URL}/api/v1/health/ready" "api readiness"

if grep -q '"status": "ok"' /tmp/ideaflow_smoke_body.txt 2>/dev/null || true; then
  :
fi

# shellcheck disable=SC2086
if docker compose ${COMPOSE_ARGS} ps --status running --services 2>/dev/null | grep -qx backend; then
  log "OK  backend container running"
  # Non-blocking production advisories (never fail smoke solely for warnings).
  # shellcheck disable=SC2086
  docker compose ${COMPOSE_ARGS} exec -T backend \
    python -c 'from app.core.config import get_settings; from app.core.production_checks import production_config_warnings; w=production_config_warnings(get_settings());
print("production warnings:", *w if w else ["none"], sep="\n  - " if w else " ")' \
    || log "WARN could not evaluate production_config_warnings"
else
  fail "backend container is not running"
fi

if [[ "${CHECK_EMBEDDING}" -eq 1 ]]; then
  # shellcheck disable=SC2086
  docker compose ${COMPOSE_ARGS} exec -T backend \
    python -c 'from app.core.config import get_settings; s=get_settings(); print("EMBEDDING_ENABLED=", s.embedding_enabled); print("EMBEDDING_MODEL_NAME=", s.embedding_model_name); print("EMBEDDING_DIMENSION=", s.embedding_dimension); print("EMBEDDING_WORKER_ENABLED=", s.embedding_worker_enabled)'
fi

if [[ "${CHECK_COVERAGE}" -eq 1 ]]; then
  # shellcheck disable=SC2086
  docker compose ${COMPOSE_ARGS} exec -T backend \
    python -m app.cli.enqueue_embeddings --coverage
fi

log "Smoke checks passed."
log "Manual follow-ups (not automated here): login, Idea list, keyword/semantic/hybrid search, Research history."
log "WARNING: Do not run pytest against production DATABASE_URL. Use TEST_DATABASE_URL only."
