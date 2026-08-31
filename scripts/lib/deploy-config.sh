# shellcheck shell=bash
# Interactive deployment configuration helpers for scripts/deploy.sh

ENV_UTIL="${REPO_ROOT}/scripts/lib/env_util.py"

is_interactive() {
  [[ -t 0 && -t 1 ]]
}

env_file_get() {
  local file="$1"
  local key="$2"
  python3 "${ENV_UTIL}" get "${file}" "${key}" 2>/dev/null || true
}

env_file_set() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 "${ENV_UTIL}" set "${file}" "${key}" "${value}"
}

env_file_set_stdin() {
  local file="$1"
  local key="$2"
  python3 "${ENV_UTIL}" set-stdin "${file}" "${key}"
}

build_database_url_stdin() {
  local user="$1"
  local database="$2"
  python3 "${ENV_UTIL}" database-url-stdin "${user}" "${database}"
}

prompt_with_default() {
  local label="$1"
  local default="$2"
  local input=""
  printf '%s [%s]: ' "${label}" "${default}" >&2
  IFS= read -r input || true
  input="${input#"${input%%[![:space:]]*}"}"
  input="${input%"${input##*[![:space:]]}"}"
  if [[ -z "${input}" ]]; then
    printf '%s' "${default}"
  else
    printf '%s' "${input}"
  fi
}

prompt_yes_no_default_yes() {
  local answer=""
  printf 'Save this configuration? [Y/n]: ' >&2
  IFS= read -r answer || true
  answer="${answer#"${answer%%[![:space:]]*}"}"
  answer="${answer%"${answer##*[![:space:]]}"}"
  answer="$(printf '%s' "${answer}" | tr '[:upper:]' '[:lower:]')"
  [[ -z "${answer}" || "${answer}" == "y" || "${answer}" == "yes" ]]
}

generate_secure_password() {
  openssl rand -hex 24
}

prompt_postgres_password() {
  local password=""

  printf 'PostgreSQL password [Enter = generate secure password]:\n' >&2
  if ! IFS= read -r -s password; then
    printf '\n' >&2
    return 1
  fi
  printf '\n' >&2
  password="${password#"${password%%[![:space:]]*}"}"
  password="${password%"${password##*[![:space:]]}"}"
  if [[ -z "${password}" ]]; then
    password="$(generate_secure_password)"
    printf 'Generated a secure PostgreSQL password.\n' >&2
  fi
  printf '%s' "${password}"
}

print_configuration_summary() {
  local deploy_mode="$1"
  local public_url="$2"
  local traefik_network="$3"
  local entrypoint="$4"
  local certresolver="$5"
  local postgres_db="$6"
  local postgres_user="$7"
  local postgres_pass_label="$8"
  local secure_cookie="$9"
  local cors_origin="${10}"
  local bind_address="${11:-}"
  local http_port="${12:-}"

  cat <<EOF >&2

Configuration summary

Deployment mode : ${deploy_mode}
EOF

  if [[ "${deploy_mode}" == "traefik" ]]; then
    cat <<EOF >&2
Public URL      : ${public_url}
Traefik network : ${traefik_network}
Entrypoint      : ${entrypoint}
Certresolver    : ${certresolver}
EOF
  else
    cat <<EOF >&2
Bind address    : ${bind_address}
HTTP port       : ${http_port}
EOF
  fi

  cat <<EOF >&2
PostgreSQL DB   : ${postgres_db}
PostgreSQL User : ${postgres_user}
PostgreSQL Pass : ${postgres_pass_label}

Secure Cookie   : ${secure_cookie}
CORS Origin     : ${cors_origin}
EOF
}

run_configuration_wizard() {
  local source_env="${REPO_ROOT}/deploy/.env.example"
  local temp_env
  local is_reconfigure=0
  local deploy_mode
  local ideaflow_host
  local public_url
  local traefik_network
  local traefik_entrypoint
  local traefik_certresolver
  local bind_address
  local http_port
  local secure_cookie
  local cors_origin
  local postgres_db
  local postgres_user
  local postgres_password
  local database_url
  local postgres_pass_label="configured"
  local old_umask

  require_command python3
  require_command openssl

  if [[ -f .env ]]; then
    is_reconfigure=1
    cp .env .env.backup
    chmod 600 .env.backup 2>/dev/null || true
    source_env=".env"
  fi

  temp_env="$(mktemp "${REPO_ROOT}/.env.wizard.XXXXXX")"
  cp "${source_env}" "${temp_env}"
  chmod 600 "${temp_env}"

  if [[ "${is_reconfigure}" -eq 0 ]]; then
    log ""
    log "IdeaFlow First Deployment Setup"
    log "-------------------------------"
    log ""
    deploy_mode="$(prompt_with_default "Deployment mode" "traefik")"
  else
    log ""
    log "IdeaFlow Configuration"
    log "----------------------"
    log ""
    deploy_mode="$(prompt_with_default "Deployment mode" "$(env_file_get "${temp_env}" IDEAFLOW_DEPLOY_MODE)")"
  fi

  case "${deploy_mode}" in
    direct | traefik) ;;
    *)
      rm -f "${temp_env}"
      fail "IDEAFLOW_DEPLOY_MODE must be 'direct' or 'traefik'."
      ;;
  esac

  if [[ "${deploy_mode}" == "traefik" ]]; then
    if [[ "${is_reconfigure}" -eq 0 ]]; then
      ideaflow_host="$(prompt_with_default "IdeaFlow host" "ideaflow.openlink.kr")"
      public_url="$(prompt_with_default "Public URL" "https://ideaflow.openlink.kr")"
      traefik_network="$(prompt_with_default "Traefik network" "traefik_proxy")"
      traefik_entrypoint="$(prompt_with_default "Traefik entrypoint" "websecure")"
      traefik_certresolver="$(prompt_with_default "Traefik certresolver" "letsencrypt")"
      secure_cookie="$(prompt_with_default "Secure cookie" "true")"
      cors_origin="$(prompt_with_default "CORS origin" "https://ideaflow.openlink.kr")"
    else
      ideaflow_host="$(prompt_with_default "IdeaFlow host" "$(env_file_get "${temp_env}" IDEAFLOW_HOST)")"
      public_url="$(prompt_with_default "Public URL" "$(env_file_get "${temp_env}" IDEAFLOW_PUBLIC_URL)")"
      traefik_network="$(prompt_with_default "Traefik network" "$(env_file_get "${temp_env}" TRAEFIK_NETWORK)")"
      traefik_entrypoint="$(prompt_with_default "Traefik entrypoint" "$(env_file_get "${temp_env}" TRAEFIK_ENTRYPOINT)")"
      traefik_certresolver="$(prompt_with_default "Traefik certresolver" "$(env_file_get "${temp_env}" TRAEFIK_CERTRESOLVER)")"
      secure_cookie="$(prompt_with_default "Secure cookie" "$(env_file_get "${temp_env}" AUTH_COOKIE_SECURE)")"
      cors_origin="$(prompt_with_default "CORS origin" "$(env_file_get "${temp_env}" CORS_ORIGINS)")"
    fi
  else
    if [[ "${is_reconfigure}" -eq 0 ]]; then
      bind_address="$(prompt_with_default "Bind address" "0.0.0.0")"
      http_port="$(prompt_with_default "HTTP port" "8080")"
      secure_cookie="$(prompt_with_default "Secure cookie" "false")"
      cors_origin="$(prompt_with_default "CORS origin" "http://localhost:8080")"
    else
      bind_address="$(prompt_with_default "Bind address" "$(env_file_get "${temp_env}" IDEAFLOW_BIND_ADDRESS)")"
      http_port="$(prompt_with_default "HTTP port" "$(env_file_get "${temp_env}" IDEAFLOW_HTTP_PORT)")"
      secure_cookie="$(prompt_with_default "Secure cookie" "$(env_file_get "${temp_env}" AUTH_COOKIE_SECURE)")"
      cors_origin="$(prompt_with_default "CORS origin" "$(env_file_get "${temp_env}" CORS_ORIGINS)")"
    fi
  fi

  if [[ "${is_reconfigure}" -eq 0 ]]; then
    postgres_db="$(prompt_with_default "PostgreSQL database" "ideaflow")"
    postgres_user="$(prompt_with_default "PostgreSQL user" "ideaflow")"
    postgres_password="$(prompt_postgres_password)"
    if [[ -z "${postgres_password}" ]]; then
      rm -f "${temp_env}"
      fail "PostgreSQL password is required."
    fi
    database_url="$(
      printf '%s' "${postgres_password}" |
        build_database_url_stdin "${postgres_user}" "${postgres_db}"
    )"
    printf '%s' "${postgres_password}" | env_file_set_stdin "${temp_env}" POSTGRES_PASSWORD
    printf '%s' "${database_url}" | env_file_set_stdin "${temp_env}" DATABASE_URL
    env_file_set "${temp_env}" POSTGRES_DB "${postgres_db}"
    env_file_set "${temp_env}" POSTGRES_USER "${postgres_user}"
  else
    postgres_db="$(env_file_get "${temp_env}" POSTGRES_DB)"
    postgres_user="$(env_file_get "${temp_env}" POSTGRES_USER)"
    postgres_pass_label="configured (unchanged)"
    printf 'PostgreSQL password : configured (unchanged)\n' >&2
  fi

  env_file_set "${temp_env}" IDEAFLOW_DEPLOY_MODE "${deploy_mode}"
  env_file_set "${temp_env}" AUTH_COOKIE_SECURE "${secure_cookie}"
  env_file_set "${temp_env}" CORS_ORIGINS "${cors_origin}"

  if [[ "${deploy_mode}" == "traefik" ]]; then
    public_url="${public_url%/}"
    env_file_set "${temp_env}" IDEAFLOW_HOST "${ideaflow_host}"
    env_file_set "${temp_env}" IDEAFLOW_PUBLIC_URL "${public_url}"
    env_file_set "${temp_env}" TRAEFIK_NETWORK "${traefik_network}"
    env_file_set "${temp_env}" TRAEFIK_ENTRYPOINT "${traefik_entrypoint}"
    env_file_set "${temp_env}" TRAEFIK_CERTRESOLVER "${traefik_certresolver}"
    print_configuration_summary \
      "${deploy_mode}" "${public_url}" "${traefik_network}" "${traefik_entrypoint}" \
      "${traefik_certresolver}" "${postgres_db}" "${postgres_user}" "${postgres_pass_label}" \
      "${secure_cookie}" "${cors_origin}"
  else
    env_file_set "${temp_env}" IDEAFLOW_BIND_ADDRESS "${bind_address}"
    env_file_set "${temp_env}" IDEAFLOW_HTTP_PORT "${http_port}"
    print_configuration_summary \
      "${deploy_mode}" "" "" "" "" "${postgres_db}" "${postgres_user}" \
      "${postgres_pass_label}" "${secure_cookie}" "${cors_origin}" \
      "${bind_address}" "${http_port}"
  fi

  if ! prompt_yes_no_default_yes; then
    rm -f "${temp_env}"
    log "Configuration cancelled."
    exit 0
  fi

  old_umask="$(umask)"
  umask 077
  mv -f "${temp_env}" .env
  chmod 600 .env
  umask "${old_umask}"
  log "Configuration saved to .env."
}

ensure_env_configured() {
  if [[ -f .env && "${DO_CONFIGURE}" -eq 0 ]]; then
    return 0
  fi

  if [[ ! -f .env ]]; then
    if ! is_interactive; then
      fail ".env does not exist and interactive setup is unavailable.

Run interactively:
  ./scripts/deploy.sh

or create:
  cp deploy/.env.example .env"
    fi
    run_configuration_wizard
    return 0
  fi

  if [[ "${DO_CONFIGURE}" -eq 1 ]]; then
    if ! is_interactive; then
      fail "Interactive configuration requires a TTY."
    fi
    run_configuration_wizard
  fi
}
