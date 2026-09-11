#!/usr/bin/env bash
# Create a PostgreSQL custom-format dump of the IdeaFlow database.
# Password is never passed on the CLI — it stays inside the db container env.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# shellcheck source=lib/compose-mode.sh
source "${SCRIPT_DIR}/lib/compose-mode.sh"

BACKUP_DIR="${REPO_ROOT}/backups"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
DO_PRUNE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/backup-postgres.sh [--prune] [--keep-days N]

Creates backups/ideaflow_YYYYMMDD_HHMMSS.dump (pg_dump -Fc).

Options:
  --prune         After a successful backup, delete *.dump older than keep-days
                  (only inside ./backups; never deletes outside that directory)
  --keep-days N   Retention for --prune (default: 7)
  --help          Show help
EOF
}

log() { printf '%s\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prune) DO_PRUNE=1 ;;
    --keep-days)
      KEEP_DAYS="${2:-}"
      [[ -n "${KEEP_DAYS}" ]] || fail "--keep-days requires a number"
      shift
      ;;
    --help|-h) usage; exit 0 ;;
    *) fail "Unknown option: $1" ;;
  esac
  shift
done

[[ -f .env ]] || fail ".env not found. Copy deploy/.env.example and configure production first."
command -v docker >/dev/null 2>&1 || fail "docker is required"

COMPOSE_ARGS="$(compose_cmd_args)"
# shellcheck disable=SC2086
if ! docker compose ${COMPOSE_ARGS} ps --status running --services 2>/dev/null | grep -qx db; then
  fail "db service is not running. Start the stack first (./scripts/deploy.sh)."
fi

mkdir -p "${BACKUP_DIR}"
stamp="$(date +%Y%m%d_%H%M%S)"
outfile="${BACKUP_DIR}/ideaflow_${stamp}.dump"

log "Writing ${outfile} ..."
# shellcheck disable=SC2086
docker compose ${COMPOSE_ARGS} exec -T db \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "${outfile}"

[[ -s "${outfile}" ]] || fail "Backup file is empty: ${outfile}"
log "Backup OK: ${outfile} ($(wc -c < "${outfile}" | tr -d ' ') bytes)"

if [[ "${DO_PRUNE}" -eq 1 ]]; then
  [[ "${KEEP_DAYS}" =~ ^[0-9]+$ ]] || fail "KEEP_DAYS must be an integer"
  # Safety: only delete under backups/ and only *.dump matching ideaflow_*.dump
  log "Pruning ideaflow_*.dump older than ${KEEP_DAYS} day(s) in ${BACKUP_DIR} ..."
  find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'ideaflow_*.dump' -mtime "+${KEEP_DAYS}" -print -delete \
    || true
fi
