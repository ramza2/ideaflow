#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

DO_BUILD=1
FORCE_RECREATE=0
MIGRATE_ONLY=0

PLACEHOLDER_PASSWORD="CHANGE_ME_USE_LONG_RANDOM_PASSWORD"

# Resolved from `docker compose config --environment` (never log these values).
DEPLOY_POSTGRES_PASSWORD=""
DEPLOY_DATABASE_URL=""
DEPLOY_HTTP_PORT=""
DEPLOY_BIND_ADDRESS=""
DEPLOY_SMOKE_HOST=""

COMPOSE_ENV_CACHE=""

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

check_env_file_exists() {
  if [[ ! -f .env ]]; then
    fail ".env 파일이 없습니다. cp deploy/.env.example .env 후 값을 설정하십시오."
  fi
}

compose_quiet_config() {
  docker compose config --quiet
}

load_compose_env_cache() {
  if [[ -n "${COMPOSE_ENV_CACHE}" ]]; then
    return 0
  fi
  COMPOSE_ENV_CACHE="$(docker compose config --environment)"
}

compose_env_value() {
  local key="$1"
  load_compose_env_cache
  awk -v key="${key}" '
    index($0, key "=") == 1 {
      print substr($0, length(key) + 2)
      exit
    }
  ' <<<"${COMPOSE_ENV_CACHE}"
}

resolve_smoke_host() {
  local bind_address="$1"
  case "${bind_address}" in
    0.0.0.0 | "")
      printf '%s' "127.0.0.1"
      ;;
    127.0.0.1)
      printf '%s' "127.0.0.1"
      ;;
    *)
      printf '%s' "${bind_address}"
      ;;
  esac
}

validate_http_port() {
  local port="$1"

  if [[ ! "${port}" =~ ^[0-9]+$ ]]; then
    fail "IDEAFLOW_HTTP_PORT must be a numeric port (got invalid value)."
  fi

  if (( port < 1 || port > 65535 )); then
    fail "IDEAFLOW_HTTP_PORT must be between 1 and 65535."
  fi
}

validate_resolved_env() {
  DEPLOY_POSTGRES_PASSWORD="$(compose_env_value POSTGRES_PASSWORD)"
  DEPLOY_DATABASE_URL="$(compose_env_value DATABASE_URL)"
  DEPLOY_HTTP_PORT="$(compose_env_value IDEAFLOW_HTTP_PORT)"
  DEPLOY_BIND_ADDRESS="$(compose_env_value IDEAFLOW_BIND_ADDRESS)"

  if [[ -z "${DEPLOY_POSTGRES_PASSWORD}" ]]; then
    fail "POSTGRES_PASSWORD is required in .env"
  fi

  if [[ "${DEPLOY_POSTGRES_PASSWORD}" == "${PLACEHOLDER_PASSWORD}" ]]; then
    fail "POSTGRES_PASSWORD placeholder 값을 변경한 뒤 배포하십시오."
  fi

  if [[ -z "${DEPLOY_DATABASE_URL}" ]]; then
    fail "DATABASE_URL is required in .env"
  fi

  if [[ "${DEPLOY_DATABASE_URL}" == *"${PLACEHOLDER_PASSWORD}"* ]]; then
    fail "DATABASE_URL에 placeholder password가 남아 있습니다. POSTGRES_PASSWORD와 동일한 값(URL encoding 필요 시 적용)으로 변경하십시오."
  fi

  if [[ -z "${DEPLOY_HTTP_PORT}" ]]; then
    DEPLOY_HTTP_PORT="8080"
  fi
  validate_http_port "${DEPLOY_HTTP_PORT}"

  DEPLOY_SMOKE_HOST="$(resolve_smoke_host "${DEPLOY_BIND_ADDRESS}")"
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

wait_for_service_healthy() {
  local service="$1"
  local timeout_seconds=120
  local interval=5
  local elapsed=0

  log "Waiting for ${service} to become healthy..."
  while (( elapsed < timeout_seconds )); do
    local container_id health
    container_id="$(docker compose ps -q "${service}" 2>/dev/null || true)"
    if [[ -n "${container_id}" ]]; then
      health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' \
        "${container_id}" 2>/dev/null || true)"
      if [[ "${health}" == "healthy" ]]; then
        log "${service} is healthy."
        return 0
      fi
    fi
    sleep "${interval}"
    elapsed=$((elapsed + interval))
  done

  fail "${service} did not become healthy. Run: docker compose ps && docker compose logs ${service}"
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

start_backend() {
  local up_args=(up -d --no-deps backend)
  if [[ "${FORCE_RECREATE}" -eq 1 ]]; then
    up_args+=(--force-recreate)
  fi
  log "Starting backend..."
  docker compose "${up_args[@]}"
  wait_for_service_healthy backend
}

start_frontend() {
  local up_args=(up -d --no-deps frontend)
  if [[ "${FORCE_RECREATE}" -eq 1 ]]; then
    up_args+=(--force-recreate)
  fi
  log "Starting frontend..."
  docker compose "${up_args[@]}"
  wait_for_service_healthy frontend
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

smoke_http() {
  local base="http://${DEPLOY_SMOKE_HOST}:${DEPLOY_HTTP_PORT}"

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
  cat <<EOF

IdeaFlow deployment completed.

URL:
http://${DEPLOY_SMOKE_HOST}:${DEPLOY_HTTP_PORT}

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
  check_env_file_exists
  compose_quiet_config
  validate_resolved_env

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

  start_backend
  start_frontend
  smoke_http
  print_summary
}

main "$@"
