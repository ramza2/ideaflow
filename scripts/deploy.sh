#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

DO_BUILD=1
FORCE_RECREATE=0
MIGRATE_ONLY=0
DO_CONFIGURE=0

PLACEHOLDER_PASSWORD="CHANGE_ME_USE_LONG_RANDOM_PASSWORD"
PLACEHOLDER_IDEAFLOW_HOST="CHANGE_ME_IDEAFLOW_HOST"
PLACEHOLDER_TRAEFIK_NETWORK="CHANGE_ME_TRAEFIK_NETWORK"

COMPOSE_FILES=(-f compose.yaml)
COMPOSE_ENV_CACHE=""

# Resolved from `docker compose config --environment` (never log secret values).
DEPLOY_MODE="direct"
DEPLOY_POSTGRES_PASSWORD=""
DEPLOY_DATABASE_URL=""
DEPLOY_HTTP_PORT=""
DEPLOY_BIND_ADDRESS=""
DEPLOY_SMOKE_HOST=""
DEPLOY_IDEAFLOW_HOST=""
DEPLOY_TRAEFIK_NETWORK=""
DEPLOY_TRAEFIK_ENTRYPOINT=""
DEPLOY_TRAEFIK_CERTRESOLVER=""
DEPLOY_PUBLIC_URL=""

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [OPTIONS]

Deploy IdeaFlow with Docker Compose.

Options:
  --build            Build images (default)
  --no-build         Skip image build; use existing images
  --force-recreate   Recreate backend and frontend containers
  --migrate-only     Start DB, wait for health, run migrations, then exit
  --configure        Re-run interactive configuration (existing .env as defaults)
  --help             Show this help message

Examples:
  ./scripts/deploy.sh
  ./scripts/deploy.sh --no-build
  ./scripts/deploy.sh --migrate-only
  ./scripts/deploy.sh --configure
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
  printf 'Check service logs with: docker compose %s logs\n' "$(compose_files_display)" >&2
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
      --configure)
        DO_CONFIGURE=1
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

compose_files_display() {
  local display=""
  local item
  for item in "${COMPOSE_FILES[@]}"; do
    display+="${item} "
  done
  printf '%s' "${display% }"
}

compose_base() {
  docker compose -f compose.yaml "$@"
}

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

check_prerequisites() {
  require_command docker
  docker compose version >/dev/null 2>&1 || fail "docker compose is not available."
  docker info >/dev/null 2>&1 || fail "Docker daemon is not accessible."
}

# shellcheck source=scripts/lib/deploy-config.sh
source "${SCRIPT_DIR}/lib/deploy-config.sh"

load_compose_env_cache() {
  if [[ -n "${COMPOSE_ENV_CACHE}" ]]; then
    return 0
  fi
  COMPOSE_ENV_CACHE="$(compose config --environment)"
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

resolve_deploy_mode_from_base() {
  COMPOSE_ENV_CACHE="$(compose_base config --environment)"
  DEPLOY_MODE="$(compose_env_value IDEAFLOW_DEPLOY_MODE)"
  if [[ -z "${DEPLOY_MODE}" ]]; then
    DEPLOY_MODE="direct"
  fi
}

setup_compose_files() {
  case "${DEPLOY_MODE}" in
    direct)
      COMPOSE_FILES+=(-f compose.direct.yaml)
      ;;
    traefik)
      COMPOSE_FILES+=(-f compose.traefik.yaml)
      ;;
    *)
      fail "IDEAFLOW_DEPLOY_MODE must be 'direct' or 'traefik' (got: ${DEPLOY_MODE})."
      ;;
  esac
}

compose_quiet_config() {
  compose_base config --quiet
  resolve_deploy_mode_from_base
  setup_compose_files
  COMPOSE_ENV_CACHE=""
  compose config --quiet
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

normalize_public_url() {
  local url="$1"
  while [[ "${url}" == */ ]]; do
    url="${url%/}"
  done
  printf '%s' "${url}"
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

validate_common_env() {
  DEPLOY_POSTGRES_PASSWORD="$(compose_env_value POSTGRES_PASSWORD)"
  DEPLOY_DATABASE_URL="$(compose_env_value DATABASE_URL)"

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
}

validate_direct_env() {
  DEPLOY_HTTP_PORT="$(compose_env_value IDEAFLOW_HTTP_PORT)"
  DEPLOY_BIND_ADDRESS="$(compose_env_value IDEAFLOW_BIND_ADDRESS)"

  if [[ -z "${DEPLOY_HTTP_PORT}" ]]; then
    DEPLOY_HTTP_PORT="8080"
  fi
  validate_http_port "${DEPLOY_HTTP_PORT}"
  DEPLOY_SMOKE_HOST="$(resolve_smoke_host "${DEPLOY_BIND_ADDRESS}")"
}

validate_traefik_env() {
  DEPLOY_IDEAFLOW_HOST="$(compose_env_value IDEAFLOW_HOST)"
  DEPLOY_TRAEFIK_NETWORK="$(compose_env_value TRAEFIK_NETWORK)"
  DEPLOY_TRAEFIK_ENTRYPOINT="$(compose_env_value TRAEFIK_ENTRYPOINT)"
  DEPLOY_TRAEFIK_CERTRESOLVER="$(compose_env_value TRAEFIK_CERTRESOLVER)"
  DEPLOY_PUBLIC_URL="$(compose_env_value IDEAFLOW_PUBLIC_URL)"

  if [[ -z "${DEPLOY_IDEAFLOW_HOST}" || "${DEPLOY_IDEAFLOW_HOST}" == "${PLACEHOLDER_IDEAFLOW_HOST}" ]]; then
    fail "IDEAFLOW_HOST is required for traefik mode (placeholder 값을 실제 hostname으로 변경하십시오)."
  fi

  if [[ -z "${DEPLOY_TRAEFIK_NETWORK}" || "${DEPLOY_TRAEFIK_NETWORK}" == "${PLACEHOLDER_TRAEFIK_NETWORK}" ]]; then
    fail "TRAEFIK_NETWORK is required for traefik mode (placeholder 값을 기존 Traefik external network 이름으로 변경하십시오)."
  fi

  if [[ -z "${DEPLOY_TRAEFIK_ENTRYPOINT}" ]]; then
    fail "TRAEFIK_ENTRYPOINT is required for traefik mode."
  fi

  if [[ -z "${DEPLOY_TRAEFIK_CERTRESOLVER}" ]]; then
    DEPLOY_TRAEFIK_CERTRESOLVER="letsencrypt"
  fi

  if [[ -z "${DEPLOY_PUBLIC_URL}" ]]; then
    fail "IDEAFLOW_PUBLIC_URL is required for traefik mode."
  fi

  DEPLOY_PUBLIC_URL="$(normalize_public_url "${DEPLOY_PUBLIC_URL}")"
}

check_traefik_network_exists() {
  if ! docker network inspect "${DEPLOY_TRAEFIK_NETWORK}" >/dev/null 2>&1; then
    fail "Traefik external network '${DEPLOY_TRAEFIK_NETWORK}' does not exist. Check the existing Traefik Docker network."
  fi
}

validate_resolved_env() {
  load_compose_env_cache
  validate_common_env

  case "${DEPLOY_MODE}" in
    direct)
      validate_direct_env
      ;;
    traefik)
      validate_traefik_env
      check_traefik_network_exists
      ;;
  esac
}

wait_for_db_healthy() {
  local timeout_seconds=120
  local interval=5
  local elapsed=0

  log "Waiting for database to become healthy..."
  while (( elapsed < timeout_seconds )); do
    if compose ps --status running --services db 2>/dev/null | grep -qx db; then
      local health
      health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' \
        "$(compose ps -q db)" 2>/dev/null || true)"
      if [[ "${health}" == "healthy" ]]; then
        log "Database is healthy."
        return 0
      fi
    fi
    sleep "${interval}"
    elapsed=$((elapsed + interval))
  done

  fail "Database did not become healthy. Run: docker compose $(compose_files_display) logs db"
}

wait_for_service_healthy() {
  local service="$1"
  local timeout_seconds=120
  local interval=5
  local elapsed=0

  log "Waiting for ${service} to become healthy..."
  while (( elapsed < timeout_seconds )); do
    local container_id health
    container_id="$(compose ps -q "${service}" 2>/dev/null || true)"
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

  fail "${service} did not become healthy. Run: docker compose $(compose_files_display) ps && docker compose $(compose_files_display) logs ${service}"
}

run_migration() {
  log "Running database migrations..."
  compose run --rm migrate
  log "Migration completed."
}

bootstrap_system_admin() {
  local exit_code=0
  compose run --rm --no-deps backend python -m app.cli.create_admin --exists || exit_code=$?
  case "${exit_code}" in
    0)
      log "SYSTEM_ADMIN already exists. Skipping admin bootstrap."
      return 0
      ;;
    1) ;;
    2)
      fail "Failed to check SYSTEM_ADMIN existence (database error)."
      ;;
    *)
      fail "Unexpected exit code from create_admin --exists: ${exit_code}"
      ;;
  esac

  if ! is_interactive; then
    fail "No SYSTEM_ADMIN exists and interactive bootstrap is unavailable.

Run interactively:
  ./scripts/deploy.sh

or:
  docker compose $(compose_files_display) run --rm --no-deps backend python -m app.cli.create_admin"
  fi

  log "No SYSTEM_ADMIN exists."
  log "Create initial administrator."
  compose run --rm --no-deps -it backend python -m app.cli.create_admin
}

start_db() {
  log "Starting database..."
  compose up -d db
  wait_for_db_healthy
}

start_backend() {
  local up_args=(up -d --no-deps backend)
  if [[ "${FORCE_RECREATE}" -eq 1 ]]; then
    up_args+=(--force-recreate)
  fi
  log "Starting backend..."
  compose "${up_args[@]}"
  wait_for_service_healthy backend
}

start_frontend() {
  local up_args=(up -d --no-deps frontend)
  if [[ "${FORCE_RECREATE}" -eq 1 ]]; then
    up_args+=(--force-recreate)
  fi
  log "Starting frontend..."
  compose "${up_args[@]}"
  wait_for_service_healthy frontend
}

fail_traefik_public_smoke() {
  fail "Container services are healthy, but Traefik public route failed.

Check:
- DNS
- TRAEFIK_NETWORK
- IDEAFLOW_HOST
- TRAEFIK_ENTRYPOINT
- TRAEFIK_CERTRESOLVER
- existing Traefik TLS configuration"
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

  if [[ "${DEPLOY_MODE}" == "traefik" ]]; then
    fail_traefik_public_smoke
  fi

  fail "${label} check failed: ${url}"
}

smoke_http_direct() {
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

smoke_http_traefik() {
  local base="${DEPLOY_PUBLIC_URL}"

  wait_for_http_ok "${base}/healthz" "Frontend healthz" 120
  wait_for_http_ok "${base}/api/v1/health" "API liveness" 120
  wait_for_http_ok "${base}/api/v1/health/ready" "API readiness" 120

  local status
  status="$(curl -s -o /dev/null -w '%{http_code}' "${base}/api/nonexistent")"
  if [[ "${status}" != "404" ]]; then
    fail_traefik_public_smoke
  fi
  log "API 404 routing OK: /api/nonexistent"
}

smoke_http() {
  case "${DEPLOY_MODE}" in
    direct)
      smoke_http_direct
      ;;
    traefik)
      smoke_http_traefik
      ;;
  esac
}

print_summary() {
  local compose_hint
  compose_hint="$(compose_files_display)"

  if [[ "${DEPLOY_MODE}" == "traefik" ]]; then
    cat <<EOF

IdeaFlow deployment completed.

Deployment mode: traefik
URL: ${DEPLOY_PUBLIC_URL}
Traefik network: ${DEPLOY_TRAEFIK_NETWORK}

Services:
$(compose ps)

Migration:
completed

Useful commands:
  docker compose ${compose_hint} ps
  docker compose ${compose_hint} logs -f backend
  docker compose ${compose_hint} exec backend python -m app.cli.create_admin
EOF
    return
  fi

  cat <<EOF

IdeaFlow deployment completed.

Deployment mode: direct
URL: http://${DEPLOY_SMOKE_HOST}:${DEPLOY_HTTP_PORT}

Services:
$(compose ps)

Migration:
completed

Useful commands:
  docker compose ${compose_hint} ps
  docker compose ${compose_hint} logs -f backend
  docker compose ${compose_hint} exec backend python -m app.cli.create_admin
EOF
}

main() {
  parse_args "$@"
  check_prerequisites
  ensure_env_configured
  compose_quiet_config
  validate_resolved_env

  if [[ "${DO_BUILD}" -eq 1 ]]; then
    log "Building images..."
    compose build
  fi

  start_db
  run_migration

  if [[ "${MIGRATE_ONLY}" -eq 1 ]]; then
    log "Migrate-only mode complete."
    exit 0
  fi

  bootstrap_system_admin
  start_backend
  start_frontend
  smoke_http
  print_summary
}

main "$@"
