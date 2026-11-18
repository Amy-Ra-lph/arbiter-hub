#!/bin/bash
# Configure PQC certificate chain: RHCS root → akamu subordinate → end-entity
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/partner-common.sh"

SITE_ENV=""
DRY_RUN=false
PHASE="all"

for arg in "$@"; do
    case "$arg" in
        --site-env=*) SITE_ENV="${arg#*=}" ;;
        --phase=*)    PHASE="${arg#*=}" ;;
        --dry-run)    DRY_RUN=true ;;
        -h|--help)
            echo "Usage: setup-pqc.sh --site-env=PATH [--phase=submit|configure|all] [--dry-run]"
            echo "Configures PQC cert chain: RHCS → akamu → end-entity certs"
            echo ""
            echo "Phases:"
            echo "  submit     Generate CSR and submit to RHCS (Phase 1)"
            echo "  configure  Configure akamu + kuipa enrollment (Phase 2-3, requires signed cert)"
            echo "  all        Run both phases (only if RHCS has auto-approval)"
            exit 0
            ;;
        *) log_err "Unknown arg: $arg"; exit 1 ;;
    esac
done

if [[ -z "$SITE_ENV" ]]; then
    log_err "Usage: setup-pqc.sh --site-env=PATH [--phase=submit|configure|all] [--dry-run]"
    exit 1
fi

if [[ "$PHASE" != "submit" && "$PHASE" != "configure" && "$PHASE" != "all" ]]; then
    log_err "Invalid --phase value: $PHASE (must be submit, configure, or all)"
    exit 1
fi

# shellcheck disable=SC1090
source "$SITE_ENV"

validate_required_vars SITE_DOMAIN RHCS_CA_URL IPA_HOSTNAME
PQC_ALGORITHM="${PQC_ALGORITHM:-ML-DSA-65}"
PQC_KEM="${PQC_KEM:-ML-KEM-768}"
AKAMU_CONFIG_DIR="/etc/akamu"
AKAMU_CERT_DIR="/etc/akamu/certs"
CSR_DIR="/tmp/akamu-pqc-setup"

run_or_dry() {
    if $DRY_RUN; then
        echo "[DRY-RUN] $*"
    else
        eval "$@"
    fi
}

CSR_CNF="${CSR_DIR}/akamu-sub-ca.cnf"
CSR_KEY="${CSR_DIR}/akamu-sub-ca.key"
CSR_FILE="${CSR_DIR}/akamu-sub-ca.csr"
SIGNED_CERT="${CSR_DIR}/akamu-sub-ca.pem"

if [[ "$PHASE" == "submit" || "$PHASE" == "all" ]]; then

# ── Phase 1: Generate akamu subordinate CA CSR ─────────────────────
log_info "Phase 1: Generating akamu subordinate CA CSR (${PQC_ALGORITHM})"

if $DRY_RUN; then
    echo "[DRY-RUN] mkdir -p ${CSR_DIR}"
    echo "[DRY-RUN] Render ${SCRIPT_DIR}/templates/akamu-subordinate-ca.cnf → ${CSR_CNF}"
    echo "[DRY-RUN]   PQC_ALGORITHM=${PQC_ALGORITHM}, SITE_DOMAIN=${SITE_DOMAIN}"
    echo "[DRY-RUN] openssl req -new -newkey ${PQC_ALGORITHM} -keyout ${CSR_KEY} -out ${CSR_FILE} -config ${CSR_CNF} -nodes"
else
    mkdir -p "$CSR_DIR"
    sed \
        -e "s|__PQC_ALGORITHM__|${PQC_ALGORITHM}|g" \
        -e "s|__SITE_DOMAIN__|${SITE_DOMAIN}|g" \
        "${SCRIPT_DIR}/templates/akamu-subordinate-ca.cnf" > "$CSR_CNF"

    openssl req -new -newkey "${PQC_ALGORITHM}" \
        -keyout "$CSR_KEY" -out "$CSR_FILE" \
        -config "$CSR_CNF" -nodes
    log_ok "CSR generated: $CSR_FILE"
fi

# ── Phase 1b: Submit CSR to RHCS ──────────────────────────────────
log_info "Phase 1b: Submitting CSR to RHCS at ${RHCS_CA_URL}"

if ! $DRY_RUN; then
    if ! curl -sk --connect-timeout 10 -o /dev/null "${RHCS_CA_URL}" 2>/dev/null; then
        log_err "RHCS CA at ${RHCS_CA_URL} is not reachable"
        log_err "Verify the URL and network connectivity before continuing"
        exit 1
    fi
fi

RHCS_PROFILE="caSubCA"
run_or_dry "pki -d /root/.dogtag/nssdb -n 'admin' -U '${RHCS_CA_URL}' ca-cert-request-submit --profile ${RHCS_PROFILE} --csr-file '${CSR_FILE}'"

echo ""
log_info "CSR submitted to RHCS. Next steps:"
echo "  1. Approve the request in RHCS admin console or CLI:"
echo "     pki -U '${RHCS_CA_URL}' ca-cert-request-approve <request-id>"
echo "  2. Download the signed certificate:"
echo "     pki -U '${RHCS_CA_URL}' ca-cert-show <cert-serial> --output ${SIGNED_CERT}"
echo "  3. Re-run: ./setup-pqc.sh --site-env=${SITE_ENV} --phase=configure"
echo ""

if [[ "$PHASE" == "submit" ]]; then
    log_ok "Phase 1 complete — waiting for RHCS certificate approval"
    exit 0
fi

fi # end submit/all phase

# ── Phase 2: Configure akamu with subordinate CA cert ─────────────
if [[ "$PHASE" == "configure" || "$PHASE" == "all" ]]; then

if ! $DRY_RUN && [[ ! -f "${SIGNED_CERT}" ]]; then
    log_err "Signed certificate not found at ${SIGNED_CERT}"
    log_err "Download it from RHCS first:"
    echo "  pki -U '${RHCS_CA_URL}' ca-cert-show <cert-serial> --output ${SIGNED_CERT}"
    echo ""
    echo "Then re-run: ./setup-pqc.sh --site-env=${SITE_ENV} --phase=configure"
    exit 1
fi

log_info "Phase 2: Configuring akamu with PQC subordinate CA"

RHCS_ROOT_CERT="${RHCS_CA_CERT:-/etc/pki/ca-trust/source/anchors/rhcs-root.pem}"

run_or_dry "mkdir -p ${AKAMU_CERT_DIR}"
run_or_dry "cp '${SIGNED_CERT}' '${AKAMU_CERT_DIR}/akamu-sub-ca.pem'"
run_or_dry "cp '${CSR_KEY}' '${AKAMU_CERT_DIR}/akamu-sub-ca.key'"
run_or_dry "chmod 600 '${AKAMU_CERT_DIR}/akamu-sub-ca.key'"

if $DRY_RUN; then
    echo "[DRY-RUN] Update akamu config:"
    echo "  signing_algorithm = ${PQC_ALGORITHM}"
    echo "  ca_cert = ${AKAMU_CERT_DIR}/akamu-sub-ca.pem"
    echo "  ca_key = ${AKAMU_CERT_DIR}/akamu-sub-ca.key"
    echo "  ca_chain = ${RHCS_ROOT_CERT}"
    echo "[DRY-RUN] systemctl restart akamu"
else
    if [[ -f "${AKAMU_CONFIG_DIR}/akamu.toml" ]]; then
        # Update signing algorithm and cert paths
        sed -i "s|^signing_algorithm.*|signing_algorithm = \"${PQC_ALGORITHM}\"|" "${AKAMU_CONFIG_DIR}/akamu.toml"
        sed -i "s|^ca_cert.*|ca_cert = \"${AKAMU_CERT_DIR}/akamu-sub-ca.pem\"|" "${AKAMU_CONFIG_DIR}/akamu.toml"
        sed -i "s|^ca_key.*|ca_key = \"${AKAMU_CERT_DIR}/akamu-sub-ca.key\"|" "${AKAMU_CONFIG_DIR}/akamu.toml"

        if ! grep -q "ca_chain" "${AKAMU_CONFIG_DIR}/akamu.toml"; then
            echo "ca_chain = \"${RHCS_ROOT_CERT}\"" >> "${AKAMU_CONFIG_DIR}/akamu.toml"
        else
            sed -i "s|^ca_chain.*|ca_chain = \"${RHCS_ROOT_CERT}\"|" "${AKAMU_CONFIG_DIR}/akamu.toml"
        fi

        systemctl restart akamu 2>/dev/null || true
        log_ok "akamu configured with ${PQC_ALGORITHM} subordinate CA"
    else
        log_err "akamu config not found at ${AKAMU_CONFIG_DIR}/akamu.toml"
        log_info "Ensure akamu is installed on the IPA node before running PQC setup"
    fi
fi

# ── Phase 3: kuipa enrollment for agent nodes ─────────────────────
log_info "Phase 3: kuipa enrollment for agent nodes"

if [[ -n "${AGENT_HOSTNAMES:-}" ]]; then
    read -ra AGENTS <<< "$AGENT_HOSTNAMES"
    for agent in "${AGENTS[@]}"; do
        log_info "Enrolling ${agent} with kuipa (${PQC_ALGORITHM})"
        run_or_dry "ssh root@${agent} 'kuipa enroll --method=otp --algorithm=${PQC_ALGORITHM} --kem=${PQC_KEM} --server=${IPA_HOSTNAME}'"
    done
else
    log_info "No AGENT_HOSTNAMES specified — skipping kuipa enrollment"
fi

# kuipa protect (sealed keytabs) blocked on upstream ACIs
log_info "Note: kuipa 'protect' (sealed keytabs) requires upstream ACI patch — skipping"
log_info "Use 'kuipa enroll' without sealing for now"

fi # end configure/all phase

log_ok "PQC setup complete (${PQC_ALGORITHM} signing, ${PQC_KEM} key exchange)"
