# Shared Compose file selection for operational scripts.
# shellcheck shell=bash

compose_mode_resolve() {
  local mode="direct"
  if [[ -f .env ]]; then
    mode="$(
      grep -E '^[[:space:]]*IDEAFLOW_DEPLOY_MODE=' .env 2>/dev/null \
        | tail -n 1 \
        | cut -d= -f2- \
        | tr -d '"' \
        | tr -d "'" \
        | tr -d '[:space:]'
    )"
    if [[ -z "${mode}" ]]; then
      mode="direct"
    fi
  fi
  case "${mode}" in
    direct|traefik) printf '%s' "${mode}" ;;
    *) printf '%s' "direct" ;;
  esac
}

compose_cmd_args() {
  local mode
  mode="$(compose_mode_resolve)"
  if [[ "${mode}" == "traefik" ]]; then
    printf '%s' "-f compose.yaml -f compose.traefik.yaml"
  else
    printf '%s' "-f compose.yaml -f compose.direct.yaml"
  fi
}
