#!/bin/bash
# Generate per-node config.env files from a single site.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/partner-common.sh"

SITE_ENV=""
OUTPUT_DIR=""

for arg in "$@"; do
    case "$arg" in
        --site-env=*) SITE_ENV="${arg#*=}" ;;
        --output=*)   OUTPUT_DIR="${arg#*=}" ;;
        -h|--help)
            echo "Usage: generate-configs.sh --site-env=PATH --output=DIR"
            echo "Splits site.env into per-node config.env files."
            exit 0
            ;;
        *) log_err "Unknown arg: $arg"; exit 1 ;;
    esac
done

if [[ -z "$SITE_ENV" || -z "$OUTPUT_DIR" ]]; then
    log_err "Usage: generate-configs.sh --site-env=PATH --output=DIR"
    exit 1
fi

if [[ ! -f "$SITE_ENV" ]]; then
    log_err "Site env not found: $SITE_ENV"
    exit 1
fi

# shellcheck disable=SC1090
source "$SITE_ENV"

REQUIRED_VARS=(
    SITE_DOMAIN SITE_REALM ADMIN_PASSWORD DS_PASSWORD DNS_FORWARDER
    IPA_HOSTNAME HUB_HOSTNAME SIGNING_HOSTNAME AGENT_HOSTNAMES RHCS_CA_URL
)
validate_required_vars "${REQUIRED_VARS[@]}"

# Auto-generate optional secrets if empty
DB_PASSWORD="${DB_PASSWORD:-$(generate_password)}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(generate_password)}"
ARBITER_SERVICE_PASSWORD="${ARBITER_SERVICE_PASSWORD:-$(generate_password)}"
COSIGN_PASSWORD="${COSIGN_PASSWORD:-$(generate_password)}"

mkdir -p "$OUTPUT_DIR"

# ── IPA config ─────────────────────────────────────────────────────
cat > "$OUTPUT_DIR/ipa-config.env" <<EOF
IDM_ROLE=primary
IDM_DOMAIN=${SITE_DOMAIN}
IDM_REALM=${SITE_REALM}
IDM_ADMIN_PASSWORD=${ADMIN_PASSWORD}
IDM_DS_PASSWORD=${DS_PASSWORD}
IDM_HOSTNAME=${IPA_HOSTNAME}
IDM_SETUP_DNS=${IPA_SETUP_DNS:-yes}
IDM_DNS_FORWARDER=${DNS_FORWARDER}
IDM_NO_REVERSE=${IPA_NO_REVERSE:-yes}
PQC_ENABLED=${PQC_ENABLED:-yes}
PQC_ALGORITHM=${PQC_ALGORITHM:-ML-DSA-65}
PQC_KEM=${PQC_KEM:-ML-KEM-768}
KUIPA_ENROLL=${KUIPA_ENROLL:-yes}
RHCS_CA_URL=${RHCS_CA_URL}
RHCS_CA_CERT=${RHCS_CA_CERT:-}
EOF

# ── Hub config ─────────────────────────────────────────────────────
cat > "$OUTPUT_DIR/hub-config.env" <<EOF
IPA_DOMAIN=${SITE_DOMAIN}
IPA_ADMIN_PASSWORD=${ADMIN_PASSWORD}
IDM_HOSTNAME=${IPA_HOSTNAME}
HUB_HOSTNAME=${HUB_HOSTNAME}
SIGNING_HOSTNAME=${SIGNING_HOSTNAME}
DB_PASSWORD=${DB_PASSWORD}
WEBHOOK_SECRET=${WEBHOOK_SECRET}
ARBITER_SERVICE_PASSWORD=${ARBITER_SERVICE_PASSWORD}
API_PORT=${API_PORT:-8400}
MCP_PORT=${MCP_PORT:-8401}
UI_PORT=${UI_PORT:-8402}
EDA_PORT=${EDA_PORT:-5001}
EOF

# ── Signing config ─────────────────────────────────────────────────
cat > "$OUTPUT_DIR/signing-config.env" <<EOF
IPA_DOMAIN=${SITE_DOMAIN}
IPA_ADMIN_PASSWORD=${ADMIN_PASSWORD}
IDM_HOSTNAME=${IPA_HOSTNAME}
SIGNING_HOSTNAME=${SIGNING_HOSTNAME}
HUB_HOSTNAME=${HUB_HOSTNAME}
COSIGN_PASSWORD=${COSIGN_PASSWORD}
REGISTRY_PORT=${REGISTRY_PORT:-5000}
EOF

# ── Agent config(s) ────────────────────────────────────────────────
# Write a base agent-config.env and per-host configs
read -ra AGENTS <<< "${AGENT_HOSTNAMES}"
FIRST_AGENT="${AGENTS[0]}"

cat > "$OUTPUT_DIR/agent-config.env" <<EOF
IPA_DOMAIN=${SITE_DOMAIN}
IPA_ADMIN_PASSWORD=${ADMIN_PASSWORD}
IDM_HOSTNAME=${IPA_HOSTNAME}
HUB_HOSTNAME=${HUB_HOSTNAME}
HUB_API_URL=https://${HUB_HOSTNAME}
SIGNING_HOSTNAME=${SIGNING_HOSTNAME}
ARBITER_SERVICE_PASSWORD=${ARBITER_SERVICE_PASSWORD}
AGENT_HOSTNAME=${FIRST_AGENT}
EOF

for agent_host in "${AGENTS[@]}"; do
    cat > "$OUTPUT_DIR/agent-${agent_host}-config.env" <<EOF
IPA_DOMAIN=${SITE_DOMAIN}
IPA_ADMIN_PASSWORD=${ADMIN_PASSWORD}
IDM_HOSTNAME=${IPA_HOSTNAME}
HUB_HOSTNAME=${HUB_HOSTNAME}
HUB_API_URL=https://${HUB_HOSTNAME}
SIGNING_HOSTNAME=${SIGNING_HOSTNAME}
ARBITER_SERVICE_PASSWORD=${ARBITER_SERVICE_PASSWORD}
AGENT_HOSTNAME=${agent_host}
EOF
done

log_ok "Generated configs in $OUTPUT_DIR: ipa, hub, signing, ${#AGENTS[@]} agent(s)"
