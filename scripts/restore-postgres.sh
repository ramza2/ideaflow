#!/usr/bin/env bash
# Restore an IdeaFlow pg_dump -Fc backup.
#
# Default: restore into a separate database ideaflow_restore_test (safe validation).
# Production overwrite requires --confirm-production.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# shellcheck source=lib/compose-mode.sh
source "${SCRIPT_DIR}/lib/compose-mode.sh"

DUMP_FILE=""
TARGET_DB="ideaflow_restore_test"
CONFIRM_PRODUCTION=0

usage() {
  cat <<'EOF'
Usage: ./scripts/restore-postgres.sh --dump backups/ideaflow_YYYYMMDD_HHMMSS.dump [options]

Options:
  --dump PATH                 Required. Custom-format dump from backup-postgres.sh
  --target-db NAME            Target database (default: ideaflow_restore_test)
  --confirm-production        Required when --target-db matches production POSTGRES_DB
  --help

Examples:
  # Safe restore verification (recommended)
  ./scripts/restore-postgres.sh --dump backups/ideaflow_20260911_120000.dump

  # Dangerous: overwrite production DB (after taking a fresh backup)
  ./scripts/restore-postgres.sh --dump backups/...dump --target-db ideaflow --confirm-production
EOF
}

log() { printf '%s\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dump)
      DUMP_FILE="${2:-}"
      shift
      ;;
    --target-db)
      TARGET_DB="${2:-}"
      shift
      ;;
    --confirm-production) CONFIRM_PRODUCTION=1 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "Unknown option: $1" ;;
  esac
  shift
done

[[ -n "${DUMP_FILE}" ]] || fail "--dump is required"
[[ -f "${DUMP_FILE}" ]] || fail "Dump file not found: ${DUMP_FILE}"
[[ -f .env ]] || fail ".env not found"
command -v docker >/dev/null 2>&1 || fail "docker is required"

DUMP_ABS="$(cd "$(dirname "${DUMP_FILE}")" && pwd)/$(basename "${DUMP_FILE}")"
COMPOSE_ARGS="$(compose_cmd_args)"

# shellcheck disable=SC2086
if ! docker compose ${COMPOSE_ARGS} ps --status running --services 2>/dev/null | grep -qx db; then
  fail "db service is not running."
fi

# shellcheck disable=SC2086
PROD_DB="$(docker compose ${COMPOSE_ARGS} exec -T db printenv POSTGRES_DB | tr -d '\r')"
[[ -n "${PROD_DB}" ]] || fail "Could not read POSTGRES_DB from db container"

if [[ "${TARGET_DB}" == "${PROD_DB}" && "${CONFIRM_PRODUCTION}" -ne 1 ]]; then
  fail "Refusing to restore into production database '${PROD_DB}' without --confirm-production.
Take a fresh backup first. Prefer --target-db ideaflow_restore_test for verification."
fi

log "Restoring ${DUMP_ABS} → database '${TARGET_DB}' ..."

# Create target DB if missing.
# shellcheck disable=SC2086
docker compose ${COMPOSE_ARGS} exec -T db \
  env TARGET_DB="${TARGET_DB}" \
  sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -tc "SELECT 1 FROM pg_database WHERE datname = '\''$TARGET_DB'\''" | grep -q 1 || \
         psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$TARGET_DB\" OWNER \"$POSTGRES_USER\";"'

# shellcheck disable=SC2086
docker compose ${COMPOSE_ARGS} exec -T db \
  env TARGET_DB="${TARGET_DB}" \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" --clean --if-exists --no-owner --no-acl' \
  < "${DUMP_ABS}"

log "Restore finished for '${TARGET_DB}'."
if [[ "${TARGET_DB}" != "${PROD_DB}" ]]; then
  log "Non-production restore complete. Application still uses '${PROD_DB}'."
  log "Verify: docker compose ${COMPOSE_ARGS} exec db psql -U \"\$POSTGRES_USER\" -d ${TARGET_DB} -c '\\dt'"
else
  log "Production database overwritten. Restart backend and run ./scripts/smoke-production.sh"
fi
