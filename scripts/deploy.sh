#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

DO_BUILD=1
FORCE_RECREATE=0
MIGRATE_ONLY=0

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [OPTIONS]

Deploy IdeaFlow with Docker Compose.

Options:
  --build            Build images (default)
  --no-build         Skip image build; use existing images
  --force-recreate   Recreate backend and frontend containers
  --migrate-only     Start DB, wait for health, run migrations, then exit
  --help             Show this help message

Examples:
  ./scripts/deploy.sh
  ./scripts/deploy.sh --no-build
  ./scripts/deploy.sh --migrate-only
EOF
}

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local line="${1:-unknown}"
  printf 'Deployment failed near line %s.\n' "${line}" >&2
  printf 'Check service logs with: docker compose logs\n' >&2
}

trap 'on_error ${LINENO}' ERR

parse_args() {
  if [[ $# -eq 0 ]]; then
    return
  fi
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --build)
        DO_BUILD=1
        ;;
      --no-build)
        DO_BUILD=0
        ;;
      --force-recreate)
        FORCE_RECREATE=1
        ;;
      --migrate-only)
        MIGRATE_ONLY=1
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        fail "Unknown option: $1 (use --help)"
        ;;
    esac
    shift
  done
}

require_command() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || fail "${cmd} is required but not found."
}

check_prerequisites() {
  require_command docker
  docker compose version >/dev/null 2>&1 || fail "docker compose is not available."
  docker info >/dev/null 2>&1 || fail "Docker daemon is not accessible."
}

validate_env_file() {
  if [[ ! -f .env ]]; then
    fail ".env 파일이 없습니다. cp deploy/.env.example .env 후 값을 설정하십시오."
  fi

  # shellcheck disable=SC1091
  set -a
  source .env
  set +a

  if [[ "${POSTGRES_PASSWORD:-}" == "CHANGE_ME_USE_LONG_RANDOM_PASSWORD" ]]; then
    fail "POSTGRES_PASSWORD placeholder 값을 변경한 뒤 배포하십시오."
  fi

  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    fail "POSTGRES_PASSWORD is required in .env"
  fi
}

compose_quiet_config() {
  docker compose config --quiet
}

wait_for_db_healthy() {
  local timeout_seconds=120
  local interval=5
  local elapsed=0

  log "Waiting for database to become healthy..."
  while (( elapsed < timeout_seconds )); do
    if docker compose ps --status running --services db 2>/dev/null | grep -qx db; then
      local health
      health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' \
        "$(docker compose ps -q db)" 2>/dev/null || true)"
      if [[ "${health}" == "healthy" ]]; then
        log "Database is healthy."
        return 0
      fi
    fi
    sleep "${interval}"
    elapsed=$((elapsed + interval))
  done

  fail "Database did not become healthy. Run: docker compose logs db"
}

run_migration() {
  log "Running database migrations..."
  docker compose run --rm migrate
  log "Migration completed."
}

start_db() {
  log "Starting database..."
  docker compose up -d db
  wait_for_db_healthy
}

start_application() {
  local up_args=(up -d backend frontend)
  if [[ "${FORCE_RECREATE}" -eq 1 ]]; then
    up_args+=(--force-recreate)
  fi
  log "Starting backend and frontend..."
  docker compose "${up_args[@]}"
}

wait_for_http_ok() {
  local url="$1"
  local label="$2"
  local timeout_seconds="${3:-120}"
  local interval=5
  local elapsed=0

  require_command curl

  while (( elapsed < timeout_seconds )); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      log "${label} OK: ${url}"
      return 0
    fi
    sleep "${interval}"
    elapsed=$((elapsed + interval))
  done

  fail "${label} check failed: ${url}"
}

wait_for_services_healthy() {
  local timeout_seconds=120
  local interval=5
  local elapsed=0

  log "Waiting for backend and frontend health checks..."
  while (( elapsed < timeout_seconds )); do
    local backend_health frontend_health
    backend_health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' \
      "$(docker compose ps -q backend)" 2>/dev/null || true)"
    frontend_health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' \
      "$(docker compose ps -q frontend)" 2>/dev/null || true)"
    if [[ "${backend_health}" == "healthy" && "${frontend_health}" == "healthy" ]]; then
      log "Backend and frontend are healthy."
      return 0
    fi
    sleep "${interval}"
    elapsed=$((elapsed + interval))
  done

  fail "Services did not become healthy. Run: docker compose ps && docker compose logs backend frontend"
}

smoke_http() {
  local port="${IDEAFLOW_HTTP_PORT:-8080}"
  local base="http://127.0.0.1:${port}"

  wait_for_http_ok "${base}/healthz" "Frontend healthz" 120
  wait_for_http_ok "${base}/api/v1/health" "API liveness" 120
  wait_for_http_ok "${base}/api/v1/health/ready" "API readiness" 120

  local status
  status="$(curl -s -o /dev/null -w '%{http_code}' "${base}/api/nonexistent")"
  if [[ "${status}" != "404" ]]; then
    fail "Expected /api/nonexistent to return 404, got ${status}"
  fi
  log "API 404 routing OK: /api/nonexistent"
}

print_summary() {
  local port="${IDEAFLOW_HTTP_PORT:-8080}"
  cat <<EOF

IdeaFlow deployment completed.

URL:
http://127.0.0.1:${port}

Services:
$(docker compose ps)

Migration:
completed

Useful commands:
  docker compose ps
  docker compose logs -f backend
  docker compose exec backend python -m app.cli.create_admin
EOF
}

main() {
  parse_args "$@"
  check_prerequisites
  validate_env_file
  compose_quiet_config

  if [[ "${DO_BUILD}" -eq 1 ]]; then
    log "Building images..."
    docker compose build
  fi

  start_db
  run_migration

  if [[ "${MIGRATE_ONLY}" -eq 1 ]]; then
    log "Migrate-only mode complete."
    exit 0
  fi

  start_application
  wait_for_services_healthy
  smoke_http
  print_summary
}

main "$@"
