#!/bin/bash
# Shared utilities for partner onboarding scripts

# Source arbiter-hub common.sh if available, otherwise standalone
PARTNER_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTC_COMMON="${PARTNER_LIB_DIR}/../../bootc/lib/common.sh"
if [[ -f "$BOOTC_COMMON" ]]; then
    # shellcheck disable=SC1090
    source "$BOOTC_COMMON"
else
    LOG_PREFIX="[partner]"
    log_info() { echo "${LOG_PREFIX} INFO: $*"; }
    log_err()  { echo "${LOG_PREFIX} ERROR: $*" >&2; }
    log_ok()   { echo "${LOG_PREFIX} OK: $*"; }
fi

validate_site_env() {
    local site_env="$1"
    local missing=0

    while IFS= read -r line; do
        [[ "$line" =~ ^#.*\(REQUIRED\) ]] && continue
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^# ]] && continue

        local key="${line%%=*}"
        local rest="${line#*=}"
        local value="${rest%%#*}"
        value="$(echo "$value" | xargs)" # trim whitespace

        if grep -q "(REQUIRED)" <<< "$line" || grep -q "(REQUIRED)" <<< "$(grep "^${key}=" "$site_env")"; then
            :
        else
            continue
        fi

        if [[ -z "$value" ]]; then
            log_err "Required field not set: $key"
            missing=$((missing + 1))
        fi
    done < "$site_env"

    # Direct check: parse REQUIRED fields from the example, verify in sourced env
    if [[ $missing -gt 0 ]]; then
        return 1
    fi
}

validate_required_vars() {
    local -a required=("$@")
    local missing=0
    for var in "${required[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_err "Required field not set: $var"
            missing=$((missing + 1))
        fi
    done
    if [[ $missing -gt 0 ]]; then
        return 1
    fi
}

generate_password() {
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))' 2>/dev/null || \
        openssl rand -base64 24 2>/dev/null || \
        head -c 24 /dev/urandom | base64
}
