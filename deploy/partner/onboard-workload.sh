#!/bin/bash
# Onboard a workload to IPA (identity) + Arbiter Hub (attestation)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/partner-common.sh"

TYPE=""
NAME=""
IMAGE=""
HUB_URL=""
IPA_DOMAIN=""
IPA_HOSTNAME=""
DRY_RUN=false
PQC_ALGORITHM="${PQC_ALGORITHM:-ML-DSA-65}"
PQC_KEM="${PQC_KEM:-ML-KEM-768}"

for arg in "$@"; do
    case "$arg" in
        --type=*)         TYPE="${arg#*=}" ;;
        --name=*)         NAME="${arg#*=}" ;;
        --image=*)        IMAGE="${arg#*=}" ;;
        --hub-url=*)      HUB_URL="${arg#*=}" ;;
        --ipa-domain=*)   IPA_DOMAIN="${arg#*=}" ;;
        --ipa-hostname=*) IPA_HOSTNAME="${arg#*=}" ;;
        --dry-run)        DRY_RUN=true ;;
        -h|--help)
            echo "Usage: onboard-workload.sh --type=container|vm|bare-metal|edge --name=NAME"
            echo "                           [--image=IMAGE] [--hub-url=URL] [--ipa-domain=DOMAIN]"
            echo "                           [--ipa-hostname=FQDN] [--dry-run]"
            exit 0
            ;;
        *) log_err "Unknown arg: $arg"; exit 1 ;;
    esac
done

if [[ -z "$TYPE" || -z "$NAME" ]]; then
    log_err "Required: --type= and --name="
    exit 1
fi

if [[ -z "$HUB_URL" ]]; then
    HUB_URL="https://${HUB_HOSTNAME:-hub.$(hostname -d)}"
fi
if [[ -z "$IPA_DOMAIN" ]]; then
    IPA_DOMAIN="$(hostname -d 2>/dev/null || echo 'example.corp')"
fi

REALM=$(echo "$IPA_DOMAIN" | tr '[:lower:]' '[:upper:]')

run_or_dry() {
    if $DRY_RUN; then
        echo "[DRY-RUN] $*"
    else
        eval "$@"
    fi
}

get_token() {
    if $DRY_RUN; then
        echo "[DRY-RUN] curl -sk -u \$CLIENT_ID:\$CLIENT_SECRET -X POST https://\$IPA_HOSTNAME/idp/token -d grant_type=client_credentials"
        echo "TOKEN=<service-token>"
        return
    fi
    local ipa_host="${IPA_HOSTNAME:-ipa.${IPA_DOMAIN}}"
    TOKEN=$(curl -sk --negotiate -u : \
        -X POST "https://${ipa_host}/idp/token" \
        -d "grant_type=client_credentials&scope=openid" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
    if [[ -z "$TOKEN" ]]; then
        log_err "Failed to get service token from ahdapa"
        return 1
    fi
}

query_state() {
    local workload_id="$1"
    if $DRY_RUN; then
        echo "[DRY-RUN] curl -sk -H 'Authorization: Bearer \$TOKEN' ${HUB_URL}:8400/api/v1/workloads/${workload_id}/state"
        echo "Workload ${NAME} enrolled — state: REGISTERED"
        return
    fi
    local state
    state=$(curl -sk -H "Authorization: Bearer ${TOKEN}" \
        "${HUB_URL}:8400/api/v1/workloads/${workload_id}/state" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
    log_ok "Workload ${NAME} enrolled — state: ${state}"
}

# ── Container workload ─────────────────────────────────────────────
onboard_container() {
    log_info "Onboarding container workload: ${NAME}"

    # 1. Create IPA service identity (idempotent)
    run_or_dry "ipa service-show container/${NAME}@${REALM} 2>/dev/null || ipa service-add container/${NAME}@${REALM}"

    # 2. kuipa enrollment
    run_or_dry "kuipa enroll --method=otp --service=container/${NAME} --algorithm=${PQC_ALGORITHM}"

    # 3. Get service token
    get_token

    # 4. Register with Hub
    run_or_dry "curl -sk -H 'Authorization: Bearer \${TOKEN}' -X POST '${HUB_URL}:8400/api/v1/workloads' -H 'Content-Type: application/json' -d '{\"name\":\"${NAME}\",\"type\":\"container\",\"cosign_verified\":true}'"

    # 5. cosign sign if image provided
    if [[ -n "$IMAGE" ]]; then
        run_or_dry "cosign sign --key arbiter-hub://${HUB_URL#https://}:8400/signing/key ${IMAGE}"
    fi

    query_state "$NAME"
}

# ── VM workload ────────────────────────────────────────────────────
onboard_vm() {
    log_info "Onboarding VM workload: ${NAME}"

    # 1. IPA client enrollment
    run_or_dry "ipa-client-install --domain=${IPA_DOMAIN} --realm=${REALM} --unattended --force-join"

    # 2. Start keylime agent (TPM attestation)
    run_or_dry "systemctl enable --now keylime_agent"

    # 3. kuipa enrollment via existing TGT
    run_or_dry "kuipa enroll --method=tgt --algorithm=${PQC_ALGORITHM}"

    # 4. Hub enrollment via SPNEGO
    run_or_dry "curl -sk --negotiate -u : -X POST '${HUB_URL}:8400/api/v1/workloads' -H 'Content-Type: application/json' -d '{\"name\":\"${NAME}\",\"type\":\"vm\",\"keylime_verified\":true}'"

    query_state "$NAME"
}

# ── Bare-metal workload ────────────────────────────────────────────
onboard_bare_metal() {
    log_info "Onboarding bare-metal workload: ${NAME}"

    # 1. IPA client enrollment
    run_or_dry "ipa-client-install --domain=${IPA_DOMAIN} --realm=${REALM} --unattended --force-join"

    # 2. keylime agent + IMA policy
    run_or_dry "systemctl enable --now keylime_agent"
    run_or_dry "cp /etc/ima/ima-policy.example /etc/ima/ima-policy 2>/dev/null || true"

    # 3. kuipa enrollment
    run_or_dry "kuipa enroll --method=otp --algorithm=${PQC_ALGORITHM}"

    # 4. Hub enrollment with IMA
    run_or_dry "curl -sk --negotiate -u : -X POST '${HUB_URL}:8400/api/v1/workloads' -H 'Content-Type: application/json' -d '{\"name\":\"${NAME}\",\"type\":\"bare-metal\",\"keylime_verified\":true,\"ima_policy\":true}'"

    query_state "$NAME"
}

# ── Edge workload ──────────────────────────────────────────────────
onboard_edge() {
    log_info "Onboarding edge workload: ${NAME}"

    # 1. IPA client enrollment (force-join for intermittent connectivity)
    run_or_dry "ipa-client-install --domain=${IPA_DOMAIN} --realm=${REALM} --unattended --force-join"

    # 2. Offline kuipa enrollment bundle
    run_or_dry "kuipa enroll --method=offline --algorithm=${PQC_ALGORITHM} --kem=${PQC_KEM}"

    # 3. Hub enrollment with offline capability
    run_or_dry "curl -sk --negotiate -u : -X POST '${HUB_URL}:8400/api/v1/workloads' -H 'Content-Type: application/json' -d '{\"name\":\"${NAME}\",\"type\":\"edge\",\"offline_capable\":true}'"

    query_state "$NAME"
}

# ── Dispatch ───────────────────────────────────────────────────────
case "$TYPE" in
    container)  onboard_container ;;
    vm)         onboard_vm ;;
    bare-metal) onboard_bare_metal ;;
    edge)       onboard_edge ;;
    *)
        log_err "Unknown workload type: ${TYPE} (expected: container, vm, bare-metal, edge)"
        exit 1
        ;;
esac
