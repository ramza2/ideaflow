#!/usr/bin/env bash
# Lightweight semantics checks (no Docker required).
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=../lib/db-name-safety.sh
source "${REPO_ROOT}/scripts/lib/db-name-safety.sh"

pass=0
fail=0

ok() {
  printf 'OK  %s\n' "$1"
  pass=$((pass + 1))
}

bad() {
  printf 'FAIL %s\n' "$1" >&2
  fail=$((fail + 1))
}

assert_ok() {
  local label="$1"
  shift
  if "$@"; then ok "${label}"; else bad "${label}"; fi
}

assert_fail() {
  local label="$1"
  shift
  if "$@"; then bad "${label} (expected failure)"; else ok "${label}"; fi
}

assert_ok "safe name ideaflow" is_safe_db_name ideaflow
assert_ok "safe name ideaflow_restore_test" is_safe_db_name ideaflow_restore_test
assert_fail "reject hyphen" is_safe_db_name 'idea-flow'
assert_fail "reject injection" is_safe_db_name 'ideaflow;drop'
assert_fail "reject empty" is_safe_db_name ''
assert_ok "system postgres" is_system_db_name postgres
assert_ok "system template1" is_system_db_name template1
assert_fail "not system ideaflow" is_system_db_name ideaflow
assert_ok "assert safe restore-test" assert_safe_restore_target_db ideaflow_restore_test
assert_fail "assert reject postgres" assert_safe_restore_target_db postgres
assert_fail "assert reject template0" assert_safe_restore_target_db template0
assert_fail "assert reject bad chars" assert_safe_restore_target_db 'bad name'

DEPLOY="${REPO_ROOT}/scripts/deploy.sh"
RESTORE="${REPO_ROOT}/scripts/restore-postgres.sh"

if grep -q 'quiesce_app_traffic' "${DEPLOY}"; then ok "deploy has quiesce_app_traffic"; else bad "deploy missing quiesce_app_traffic"; fi
if grep -q 'stop -t 15 frontend backend' "${DEPLOY}"; then ok "deploy stops frontend backend"; else bad "deploy missing stop frontend backend"; fi

if awk '
  /quiesce_app_traffic/ { if (!q) q=NR }
  /run_migration/ { if (!m) m=NR }
  END { exit (q && m && q < m) ? 0 : 1 }
' "${DEPLOY}"; then
  ok "deploy defines quiesce before run_migration"
else
  bad "deploy defines quiesce before run_migration"
fi

if grep -n 'quiesce_app_traffic\|run_migration' "${DEPLOY}" | awk '
  /quiesce_app_traffic$/ { q=$1+0 }
  /run_migration$/ { m=$1+0 }
  END { exit (q && m && q < m) ? 0 : 1 }
'; then
  ok "deploy main calls quiesce before migration"
else
  bad "deploy main calls quiesce before migration"
fi

if awk '
  /^run_migration\(/ { in_fn=1 }
  in_fn && /^}/ { in_fn=0 }
  in_fn && /start_backend|start_frontend/ { bad=1 }
  END { exit bad ? 1 : 0 }
' "${DEPLOY}"; then
  ok "run_migration does not restart app"
else
  bad "run_migration restarts app"
fi

if grep -q 'Application remains stopped' "${DEPLOY}"; then
  ok "migration fail-closed message present"
else
  bad "deploy migration failure message missing fail-closed hint"
fi

if grep -q 'confirm-production' "${RESTORE}"; then ok "restore has confirm-production"; else bad "restore missing confirm-production"; fi
if grep -q 'assert_safe_restore_target_db' "${RESTORE}"; then ok "restore has db name guard"; else bad "restore missing db name guard"; fi
if grep -q 'stop -t 15 frontend backend' "${RESTORE}"; then ok "restore production quiesce"; else bad "restore missing production quiesce"; fi
if grep -q 'exit-on-error' "${RESTORE}"; then ok "restore exit-on-error"; else bad "restore missing --exit-on-error"; fi
if grep -q 'single-transaction' "${RESTORE}"; then ok "restore single-transaction"; else bad "restore missing --single-transaction"; fi
if grep -q 'DROP DATABASE' "${RESTORE}"; then ok "restore-test DROP DATABASE clean path"; else bad "restore-test missing DROP DATABASE"; fi
if grep -q 'Application remains stopped' "${RESTORE}"; then ok "restore keeps app stopped after production"; else bad "restore missing remains stopped message"; fi

if grep -Eqi 'Restart backend' "${RESTORE}"; then
  bad "restore still advises simple Restart backend"
else
  ok "restore does not advise simple restart"
fi

# Production DROP DATABASE must not run on production path: prepare_fresh is non-prod only.
if grep -A2 'IS_PRODUCTION_TARGET' "${RESTORE}" | grep -q 'prepare_fresh_nonprod_db'; then
  # ensure production branch does not call prepare_fresh
  :
fi
if awk '
  /if \[\[ "\$\{IS_PRODUCTION_TARGET\}" -eq 1 \]\]/ { in_prod=1; next }
  in_prod && /else/ { in_prod=0; in_else=1; next }
  in_prod && /prepare_fresh_nonprod_db/ { bad=1 }
  in_else && /prepare_fresh_nonprod_db/ { else_ok=1 }
  END { exit (bad || !else_ok) ? 1 : 0 }
' "${RESTORE}"; then
  ok "fresh drop/create only on non-production restore"
else
  bad "fresh drop/create path incorrectly wired"
fi

printf '\n%d passed, %d failed\n' "${pass}" "${fail}"
[[ "${fail}" -eq 0 ]]
