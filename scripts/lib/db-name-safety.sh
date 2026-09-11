# Shared PostgreSQL database-name guards for restore scripts.
# shellcheck shell=bash

# Returns 0 when NAME is a safe SQL identifier for CREATE/DROP DATABASE.
is_safe_db_name() {
  local name="${1:-}"
  [[ "${name}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]
}

# Returns 0 when NAME is a PostgreSQL system/template database.
is_system_db_name() {
  local name="${1:-}"
  case "${name}" in
    postgres|template0|template1) return 0 ;;
    *) return 1 ;;
  esac
}

# Fail-fast validation for restore --target-db.
assert_safe_restore_target_db() {
  local name="${1:-}"
  if ! is_safe_db_name "${name}"; then
    printf 'Error: invalid --target-db %q (allowed: ^[A-Za-z_][A-Za-z0-9_]*$).\n' "${name}" >&2
    return 1
  fi
  if is_system_db_name "${name}"; then
    printf 'Error: refusing to restore into system database %q.\n' "${name}" >&2
    return 1
  fi
  return 0
}
