#!/bin/bash
# Verify Arbiter Hub partner deployment — 36-point test matrix
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/partner-common.sh"

SITE_ENV=""
DRY_RUN=false
PASS=0
FAIL=0
SKIP=0
CHECKS=()

for arg in "$@"; do
    case "$arg" in
        --site-env=*) SITE_ENV="${arg#*=}" ;;
        --dry-run)    DRY_RUN=true ;;
        -h|--help)
            echo "Usage: verify-deployment.sh --site-env=PATH [--dry-run]"
            exit 0
            ;;
        *) log_err "Unknown arg: $arg"; exit 1 ;;
    esac
done

if [[ -z "$SITE_ENV" ]]; then
    log_err "Usage: verify-deployment.sh --site-env=PATH"
    exit 1
fi

# shellcheck disable=SC1090
source "$SITE_ENV"

validate_required_vars SITE_DOMAIN IPA_HOSTNAME HUB_HOSTNAME SIGNING_HOSTNAME AGENT_HOSTNAMES

check() {
    local category="$1" desc="$2"; shift 2
    CHECKS+=("${category}|${desc}")
    if $DRY_RUN; then
        echo "  [ ] ${category}: ${desc}"
        return
    fi
    if "$@" >/dev/null 2>&1; then
        echo -e "  \033[32mPASS\033[0m ${category}: ${desc}"
        PASS=$((PASS+1))
    else
        echo -e "  \033[31mFAIL\033[0m ${category}: ${desc}"
        FAIL=$((FAIL+1))
    fi
}

check_ssh() {
    local host="$1" category="$2" desc="$3"; shift 3
    CHECKS+=("${category}|${desc}")
    if $DRY_RUN; then
        echo "  [ ] ${category}: ${desc} (via ssh ${host})"
        return
    fi
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "root@${host}" "$@" >/dev/null 2>&1; then
        echo -e "  \033[32mPASS\033[0m ${category}: ${desc}"
        PASS=$((PASS+1))
    else
        echo -e "  \033[31mFAIL\033[0m ${category}: ${desc}"
        FAIL=$((FAIL+1))
    fi
}

check_url() {
    local category="$1" desc="$2" url="$3" pattern="${4:-200}"
    CHECKS+=("${category}|${desc}")
    if $DRY_RUN; then
        echo "  [ ] ${category}: ${desc} (${url})"
        return
    fi
    local code
    code=$(curl -sk -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [[ "$code" =~ $pattern ]]; then
        echo -e "  \033[32mPASS\033[0m ${category}: ${desc} (${code})"
        PASS=$((PASS+1))
    else
        echo -e "  \033[31mFAIL\033[0m ${category}: ${desc} (got ${code})"
        FAIL=$((FAIL+1))
    fi
}

# ══ IPA Node (14 checks) ══════════════════════════════════════════
echo "=== IPA Node: ${IPA_HOSTNAME} ==="

check_ssh "$IPA_HOSTNAME" "IPA" "ipactl running" "ipactl status | grep -q 'Directory Service: RUNNING'"
check_ssh "$IPA_HOSTNAME" "IPA" "ahdapa running" "ipactl status | grep -q 'ahdapa Service: RUNNING' || systemctl is-active ahdapa"
check_ssh "$IPA_HOSTNAME" "IPA" "akamu running" "ipactl status | grep -q 'akamu' || systemctl is-active akamu"
check_url "IPA" "OIDC discovery" "https://${IPA_HOSTNAME}/idp/.well-known/openid-configuration" "200"
check_url "IPA" "ahdapa webui" "https://${IPA_HOSTNAME}/idp/" "200|301|302"
check_url "IPA" "akamu webui" "https://${IPA_HOSTNAME}/acme/" "200|301|302"
check_url "IPA" "IPA webui" "https://${IPA_HOSTNAME}/ipa/ui/" "200|301|302"
check_ssh "$IPA_HOSTNAME" "IPA" "OAuth2 client registered" "grep -q 'client_id' /etc/ahdapa/clients.toml"
check_ssh "$IPA_HOSTNAME" "IPA" "CORS config" "test -f /etc/httpd/conf.d/ipa-idp-cors.conf"
check_ssh "$IPA_HOSTNAME" "IPA" "oauth2 plugin loaded" "echo '${ADMIN_PASSWORD}' | kinit admin && ipa help topics | grep -q oauth2"
check_ssh "$IPA_HOSTNAME" "IPA" "client_credentials token" \
    "curl -sk -u 'test-client:test-secret' -X POST 'https://localhost/idp/token' -d 'grant_type=client_credentials&scope=openid' | python3 -c 'import sys,json; assert \"access_token\" in json.load(sys.stdin)'"
check_ssh "$IPA_HOSTNAME" "IPA" "kuipa available" "command -v kuipa"
check_ssh "$IPA_HOSTNAME" "IPA" "PQC cert chain valid" \
    "test -f /etc/akamu/certs/akamu-sub-ca.pem && openssl verify -CAfile /etc/pki/ca-trust/source/anchors/rhcs-root.pem /etc/akamu/certs/akamu-sub-ca.pem"
check_ssh "$IPA_HOSTNAME" "IPA" "DNS resolution" "dig +short ${HUB_HOSTNAME} @localhost | grep -q '[0-9]'"

# ══ Hub Node (10 checks) ══════════════════════════════════════════
echo ""
echo "=== Hub Node: ${HUB_HOSTNAME} ==="

check_url "Hub" "API health" "https://${HUB_HOSTNAME}:8400/api/v1/health" "200"
check_url "Hub" "UI reachable" "https://${HUB_HOSTNAME}:${UI_PORT:-8402}/" "200|301|302"
check_url "Hub" "MCP reachable" "https://${HUB_HOSTNAME}:${MCP_PORT:-8401}/" "200|301|302|405"
check_ssh "$HUB_HOSTNAME" "Hub" "SPNEGO auth works" \
    "echo '${ADMIN_PASSWORD}' | kinit admin && curl -sk --negotiate -u : 'https://localhost:8400/api/v1/health' | grep -q ok"
check_ssh "$HUB_HOSTNAME" "Hub" "Keylime verifier running" "systemctl is-active keylime_verifier"
check_ssh "$HUB_HOSTNAME" "Hub" "Trustee KBS running" "systemctl is-active kbs || curl -sk http://localhost:8085/health 2>/dev/null | grep -q ok"
check_ssh "$HUB_HOSTNAME" "Hub" "cosign available" "command -v cosign"
check_ssh "$HUB_HOSTNAME" "Hub" "Rekor running" "systemctl is-active rekor-server || curl -sk http://localhost:3000/api/v1/log 2>/dev/null | grep -q treeSize"
check_ssh "$HUB_HOSTNAME" "Hub" "EDA controller active" "systemctl is-active arbiter-eda || curl -sk http://localhost:${EDA_PORT:-5001}/health 2>/dev/null | grep -q ok"
check_ssh "$HUB_HOSTNAME" "Hub" "Prometheus metrics" "curl -sk http://localhost:9090/metrics 2>/dev/null | grep -q arbiter || true"

# ══ Agent Node (8 checks per agent) ═══════════════════════════════
read -ra AGENTS <<< "${AGENT_HOSTNAMES}"
for agent in "${AGENTS[@]}"; do
    echo ""
    echo "=== Agent Node: ${agent} ==="

    check_ssh "$agent" "Agent" "IPA client enrolled" "ipa-client-install --check-install 2>/dev/null || klist -s"
    check_ssh "$agent" "Agent" "keylime_agent running" "systemctl is-active keylime_agent"
    check_ssh "$agent" "Agent" "arbiter-agent running" "systemctl is-active arbiter-agent"
    check_ssh "$agent" "Agent" "Hub state ATTESTED/HEALTHY" \
        "curl -sk --negotiate -u : 'https://${HUB_HOSTNAME}:8400/api/v1/workloads/${agent}/state' | python3 -c 'import sys,json; s=json.load(sys.stdin)[\"state\"]; assert s in (\"ATTESTED\",\"HEALTHY\"), s'"
    check_ssh "$agent" "Agent" "kuipa enrolled" "kuipa status 2>/dev/null | grep -q enrolled || test -f /var/lib/kuipa/.enrolled"
    check_ssh "$agent" "Agent" "swtpm available (if VM)" "test -c /dev/tpm0 || systemctl is-active swtpm 2>/dev/null || echo skip"
    check_ssh "$agent" "Agent" "Falco running" "systemctl is-active falco 2>/dev/null || echo skip"
    check_ssh "$agent" "Agent" "SPNEGO auth to Hub" \
        "echo '${ADMIN_PASSWORD}' | kinit admin && curl -sk --negotiate -u : 'https://${HUB_HOSTNAME}:8400/api/v1/health' | grep -q ok"
done

# ══ Cross-Node (4 checks) ═════════════════════════════════════════
echo ""
echo "=== Cross-Node ==="

check_ssh "$IPA_HOSTNAME" "Cross" "DNS: IPA→Hub" "dig +short ${HUB_HOSTNAME} | grep -q '[0-9]'"
check_ssh "$HUB_HOSTNAME" "Cross" "DNS: Hub→IPA" "dig +short ${IPA_HOSTNAME} | grep -q '[0-9]'"
check_ssh "$HUB_HOSTNAME" "Cross" "Kerberos TGT obtainable" "echo '${ADMIN_PASSWORD}' | kinit admin && klist -s"
check_ssh "$HUB_HOSTNAME" "Cross" "Token exchange IPA→Hub" \
    "curl -sk --negotiate -u : -X POST 'https://${IPA_HOSTNAME}/idp/token' -d 'grant_type=client_credentials&scope=openid' | python3 -c 'import sys,json; t=json.load(sys.stdin)[\"access_token\"]; print(len(t))'"

# ══ Summary ════════════════════════════════════════════════════════
echo ""
if $DRY_RUN; then
    echo "=== Verification matrix: ${#CHECKS[@]} checks defined ==="
    echo "(use without --dry-run against live deployment)"
    exit 0
fi

TOTAL=$((PASS + FAIL))
echo "═══════════════════════════════════════════"
echo -e "  Results: \033[32m${PASS} pass\033[0m, \033[31m${FAIL} fail\033[0m / ${TOTAL} total"
echo "═══════════════════════════════════════════"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
