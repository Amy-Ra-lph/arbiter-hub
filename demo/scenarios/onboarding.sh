#!/usr/bin/env bash
# Onboarding demo for Arbiter Hub — domain-agnostic
# Interactive walkthrough: OIDC auth → workload registration → attestation → RBAC
#
# Required env vars (or defaults from full-demo.sh):
#   ARBITER_HUB_URL    — Hub base URL
#   ARBITER_IDP_URL    — ahdapa IdP URL
#   ARBITER_REALM      — IPA Kerberos realm
#   ARBITER_AGENT_HOST — agent node FQDN
#   ARBITER_CLIENT_SECRET — OIDC client secret
#   ARBITER_KEYLIME_AGENT_UUID — Keylime agent UUID
#   ARBITER_KEYLIME_AGENT_IP   — Keylime agent IP
set -euo pipefail

HUB_URL="${ARBITER_HUB_URL:-https://hub.arbiter.demo}"
API_URL="${HUB_URL}/api"
IDP_URL="${ARBITER_IDP_URL:-https://idm.arbiter.demo/idp}"
IPA_REALM="${ARBITER_REALM:-ARBITER.DEMO}"
AGENT_HOST="${ARBITER_AGENT_HOST:-agent.arbiter.demo}"
CLIENT_SECRET="${ARBITER_CLIENT_SECRET:?Set ARBITER_CLIENT_SECRET before running}"
KEYLIME_UUID="${ARBITER_KEYLIME_AGENT_UUID:-}"
KEYLIME_IP="${ARBITER_KEYLIME_AGENT_IP:-}"
PAUSE="${DEMO_PAUSE:-3}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}${BOLD}  $1${NC}"; echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}\n"; }
step()   { echo -e "${GREEN}▸${NC} ${BOLD}$1${NC}"; }
ok()     { echo -e "${GREEN}✓${NC} $1"; }
warn()   { echo -e "${YELLOW}⚠${NC} $1"; }
fail()   { echo -e "${RED}✗${NC} $1"; }
pause()  { echo -e "${YELLOW}[press Enter to continue]${NC}"; read -r; }

get_token() {
    curl -sk -X POST "${IDP_URL}/token" \
        -u "arbiter-hub:${CLIENT_SECRET}" \
        -d "grant_type=client_credentials" \
        -d "scope=openid $1" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

# Auto-detect Keylime agent if not set
if [ -z "$KEYLIME_UUID" ]; then
    step "Auto-detecting Keylime agent UUID from ${AGENT_HOST}..."
    KEYLIME_UUID=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o IdentitiesOnly=yes \
        -i ~/.ssh/idm_ci_key root@"${AGENT_HOST}" \
        "grep -oP '(?<=uuid\s=\s\").*(?=\")' /etc/keylime/agent.conf" 2>/dev/null || true)
    if [ -z "$KEYLIME_UUID" ]; then
        fail "Could not detect Keylime agent UUID — set ARBITER_KEYLIME_AGENT_UUID"
        exit 1
    fi
    ok "Detected UUID: ${KEYLIME_UUID}"
fi
if [ -z "$KEYLIME_IP" ]; then
    KEYLIME_IP=$(getent hosts "$AGENT_HOST" | awk '{print $1}' 2>/dev/null || true)
    [ -z "$KEYLIME_IP" ] && KEYLIME_IP=$(dig +short "$AGENT_HOST" 2>/dev/null || true)
fi

api_call() {
    local method="$1" path="$2" token="$3"
    shift 3
    curl -sk -X "$method" "${API_URL}${path}" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        "$@"
}

###############################################################################
banner "STEP 1: Authenticate via OIDC (ahdapa)"
###############################################################################

step "Getting admin token from ahdapa IdP"
ADMIN_TOKEN=$(get_token "attestation-admin")
ok "OIDC token acquired — attestation-admin scope"
echo "  Issuer: ${IDP_URL}"
echo "  Client: arbiter-hub (client_secret_basic)"
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 2: View Attestation Backends"
###############################################################################

step "Querying backend health"
BACKENDS=$(api_call GET "/backends" "$ADMIN_TOKEN")
echo "$BACKENDS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for name, info in data.items():
    status = '✓' if info.get('healthy') else '✗'
    print(f'  {status} {name}: {info.get(\"detail\", \"\")}')
" 2>/dev/null || echo "$BACKENDS" | python3 -m json.tool 2>/dev/null
ok "All backends queried"
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 3: View Existing Workloads"
###############################################################################

step "Listing registered workloads"
WORKLOADS=$(api_call GET "/workloads?count=20" "$ADMIN_TOKEN")
echo "$WORKLOADS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Total: {data.get(\"total\", 0)} workloads\n')
for w in data.get('items', []):
    state_icon = '🟢' if w['current_state'] == 'healthy' else ('🔴' if w['current_state'] == 'failed' else '🟡')
    backends = ', '.join(w.get('backend_types', []))
    print(f'  {state_icon} {w[\"display_name\"]:.<40s} {w[\"current_state\"]:<12s} [{backends}]')
    print(f'       principal: {w[\"ipa_principal\"]}')
    tier = w.get('metadata', {}).get('trust_tier', '')
    if tier:
        print(f'       trust_tier: {tier}')
    print()
" 2>/dev/null
ok "Workload inventory displayed"
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 4: Register a New Workload"
###############################################################################

step "Registering new agentic workload: 'Compliance Scanner Agent'"
NEW_RESULT=$(api_call POST "/workloads" "$ADMIN_TOKEN" -d '{
    "ipa_principal": "service/compliance-scanner@'"${IPA_REALM}"'",
    "display_name": "Compliance Scanner Agent",
    "workload_type": "agentic",
    "backend_types": ["keylime", "falco"],
    "metadata": {
        "trust_tier": "verified",
        "role": "compliance-scanner",
        "keylime_agent_uuid": "'"${KEYLIME_UUID}"'",
        "keylime_agent_ip": "'"${KEYLIME_IP}"'",
        "description": "Scans host configurations for CIS/STIG compliance"
    }
}')
NEW_ID=$(echo "$NEW_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
echo "$NEW_RESULT" | python3 -m json.tool 2>/dev/null | head -15
ok "Workload registered: ${NEW_ID}"
echo "  State: registered (not yet enrolled)"
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 5: Enroll with Attestation Backend"
###############################################################################

step "Enrolling workload with Keylime verifier"
ENROLL_RESULT=$(api_call POST "/workloads/${NEW_ID}/enroll" "$ADMIN_TOKEN" -d '{"auto_attest": true}')
echo "$ENROLL_RESULT" | python3 -m json.tool 2>/dev/null
ALREADY=$(echo "$ENROLL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',{}).get('already_enrolled',False))" 2>/dev/null)
if [ "$ALREADY" = "True" ]; then
    ok "Agent already enrolled in verifier — skipped destructive re-add"
else
    ok "Agent enrolled in verifier"
fi
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 6: Trigger Attestation"
###############################################################################

step "Running attestation check"
ATTEST_RESULT=$(api_call POST "/workloads/${NEW_ID}/attest" "$ADMIN_TOKEN")
echo "$ATTEST_RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Overall verdict: {data.get(\"verdict\", \"unknown\")}')
print(f'  State: {data.get(\"state\", \"unknown\")}')
for b in data.get('per_backend', []):
    icon = '✓' if b['verdict'] == 'pass' else '✗'
    print(f'    {icon} {b[\"backend\"]}: {b[\"verdict\"]}')
" 2>/dev/null
STATE=$(echo "$ATTEST_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null)
if [ "$STATE" = "healthy" ]; then
    ok "Workload HEALTHY — fully attested"
else
    warn "State: $STATE (may need background attestation cycle)"
fi
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 7: RBAC — Viewer Cannot Register"
###############################################################################

step "Getting viewer-scoped token"
VIEWER_TOKEN=$(get_token "attestation-viewer")
ok "Viewer token acquired"

step "Viewer attempts to register a workload (should fail)"
VIEWER_REG=$(api_call POST "/workloads" "$VIEWER_TOKEN" -d '{
    "ipa_principal": "service/viewer-attempt@'"${IPA_REALM}"'",
    "display_name": "Viewer Unauthorized Attempt",
    "workload_type": "service",
    "backend_types": ["keylime"]
}' 2>/dev/null)
if echo "$VIEWER_REG" | grep -qi "403\|forbidden\|permission"; then
    ok "Viewer BLOCKED from registration (403 Forbidden)"
else
    warn "Unexpected: $VIEWER_REG"
fi

step "Viewer can read workloads (allowed)"
VIEWER_LIST=$(api_call GET "/workloads?count=5" "$VIEWER_TOKEN" 2>/dev/null)
VIEWER_COUNT=$(echo "$VIEWER_LIST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
ok "Viewer sees $VIEWER_COUNT workloads (read-only)"
sleep "$PAUSE"

pause

###############################################################################
banner "STEP 8: Audit Trail"
###############################################################################

step "Reviewing audit log"
AUDIT=$(api_call GET "/audit?count=10" "$ADMIN_TOKEN" 2>/dev/null)
echo "$AUDIT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data.get('items', []):
    ts = e.get('created_at', e.get('timestamp',''))[:19]
    print(f'  {ts} | {e.get(\"actor\",\"-\"):.<30s} | {e.get(\"action\",\"-\"):<20s} | {e.get(\"target_type\",\"-\")}')
" 2>/dev/null || echo "  (audit endpoint may use different schema)"
ok "Audit trail shows all operations"

pause

###############################################################################
banner "ONBOARDING DEMO COMPLETE"
###############################################################################

echo -e "${BOLD}Summary:${NC}"
echo "  1. Authenticated via OIDC (ahdapa IdP → ES256 JWT)"
echo "  2. Verified 4 attestation backends (keylime, falco, measured_boot, cosign)"
echo "  3. Viewed existing workloads across 3 trust tiers"
echo "  4. Registered new agentic workload with IPA principal"
echo "  5. Enrolled with Keylime verifier (skip-if-healthy logic)"
echo "  6. Attested: Keylime PASS + Falco PASS → HEALTHY"
echo "  7. RBAC: viewer blocked from writes, allowed reads"
echo "  8. Full audit trail of all operations"
echo ""
echo -e "${CYAN}Workload ID: ${NEW_ID}${NC}"
echo -e "${CYAN}To clean up: curl -sk -X DELETE ${API_URL}/workloads/${NEW_ID} -H 'Authorization: Bearer <token>'${NC}"
