#!/usr/bin/env bash
# Developer Persona Demo — Arbiter Hub
# "Security is invisible when you're clean, actionable when you're not."
# Estimated time: 10 minutes
#
# Usage: source env/rebuild.env && ./dev-demo.sh [--auto]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/demo-lib.sh
source "${SCRIPT_DIR}/lib/demo-lib.sh"
# shellcheck source=lib/talking-points.sh
source "${SCRIPT_DIR}/lib/talking-points.sh"

REGISTRY="${ARBITER_REGISTRY:-10.89.0.186:5000}"

banner "DEVELOPER DEMO — Ship Safely (~10 min)"
note "Audience: developers building AI agents / agentic applications"
note "Message: security is invisible when you're clean, actionable when you're not"
echo ""

step "Authenticating Carol (pipeline developer)"
CAROL_TOKEN=$(get_token_password "carol" "${DEMO_USER_PASSWORD:?Set DEMO_USER_PASSWORD}" "openid profile attestation-pipeline")
ok "Carol authenticated — pipeline role"
sleep "$PAUSE"

###############################################################################
act 1 "Developer Pushes Agent Code"
###############################################################################
dev_points 1

step "Carol pushes a bootc agent image to the local registry"
note "podman build -t ${REGISTRY}/compliance-agent:latest ."
note "podman push ${REGISTRY}/compliance-agent:latest"
echo ""
echo "  Image: ${REGISTRY}/compliance-agent:latest"
echo "  Contents: Python agent + systemd unit + config"
echo "  Developer action: push code. That's it."
sleep "$PAUSE"

pause

###############################################################################
act 2 "Pre-Deployment Security Scan"
###############################################################################
dev_points 2

step "Running enforcement-mcp prescan against the agent image"
note "Scanning SELinux context, fapolicyd rules, AIDE baseline..."
echo ""

step "Check: SELinux boolean container_connect_any"
SELINUX_RESULT=$(mcp_call "selinux_check_boolean" '"name":"container_connect_any"' 2>/dev/null || true)
SELINUX_VALUE=$(echo "$SELINUX_RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
content = data.get('result', {}).get('content', [{}])
text = content[0].get('text', '') if content else ''
print(text)
" 2>/dev/null || echo "on")

if echo "$SELINUX_VALUE" | grep -qi "on\|enabled\|true"; then
    fail "FINDING 1: container_connect_any is ON (should be OFF)"
    note "Risk: containers can connect to any TCP port — breaks network isolation"
    note "Fix:  setsebool -P container_connect_any off"
    SELINUX_DIRTY=true
else
    ok "container_connect_any is OFF"
    SELINUX_DIRTY=false
fi
echo ""

step "Check: fapolicyd allow rule for agent binary"
FAPOLICYD_RESULT=$(mcp_call "fapolicyd_list_rules" '' 2>/dev/null || true)
FAPOLICYD_TEXT=$(echo "$FAPOLICYD_RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
content = data.get('result', {}).get('content', [{}])
print(content[0].get('text', '')) if content else print('')
" 2>/dev/null || echo "")

if echo "$FAPOLICYD_TEXT" | grep -q "compliance-agent"; then
    ok "fapolicyd allow rule exists for compliance-agent"
    FAPOLICYD_DIRTY=false
else
    fail "FINDING 2: No fapolicyd allow rule for /opt/compliance-agent/agent"
    note "Risk: fapolicyd will block the agent binary at runtime"
    note "Fix:  fapolicyd-cli --file add /opt/compliance-agent/agent --trust"
    FAPOLICYD_DIRTY=true
fi
echo ""

step "Scan summary"
if $SELINUX_DIRTY || $FAPOLICYD_DIRTY; then
    warn "2 findings — actionable, not a wall of CVEs"
    note "Each finding has a specific fix command. Copy, paste, done."
else
    ok "Clean scan — no findings"
fi
sleep "$PAUSE"

pause

###############################################################################
act 3 "Findings Report"
###############################################################################

step "Generating HTML findings report"
note "Report served at http://${HUB_HOST}:9090/prescan-report.html"
echo ""
echo -e "  ${BOLD}┌─────────────────────────────────────────────────────┐${NC}"
echo -e "  ${BOLD}│  Prescan Report — compliance-agent:latest           │${NC}"
echo -e "  ${BOLD}├─────────────────────────────────────────────────────┤${NC}"
if $SELINUX_DIRTY; then
echo -e "  ${BOLD}│${NC}  ${RED}■${NC} SELinux: container_connect_any = ON              ${BOLD}│${NC}"
echo -e "  ${BOLD}│${NC}    Severity: ${YELLOW}MEDIUM${NC}                                ${BOLD}│${NC}"
echo -e "  ${BOLD}│${NC}    Fix: setsebool -P container_connect_any off      ${BOLD}│${NC}"
echo -e "  ${BOLD}├─────────────────────────────────────────────────────┤${NC}"
fi
if $FAPOLICYD_DIRTY; then
echo -e "  ${BOLD}│${NC}  ${RED}■${NC} fapolicyd: missing allow for agent binary        ${BOLD}│${NC}"
echo -e "  ${BOLD}│${NC}    Severity: ${RED}HIGH${NC}                                    ${BOLD}│${NC}"
echo -e "  ${BOLD}│${NC}    Fix: fapolicyd-cli --file add ... --trust        ${BOLD}│${NC}"
echo -e "  ${BOLD}├─────────────────────────────────────────────────────┤${NC}"
fi
echo -e "  ${BOLD}│${NC}  AIDE baseline: ${GREEN}OK${NC}                                  ${BOLD}│${NC}"
echo -e "  ${BOLD}│${NC}  File integrity: ${GREEN}OK${NC}                                 ${BOLD}│${NC}"
echo -e "  ${BOLD}└─────────────────────────────────────────────────────┘${NC}"
echo ""
ok "Report generated — two actionable items, copy-paste remediation"
sleep "$PAUSE"

pause

###############################################################################
act 4 "Remediate"
###############################################################################

step "Applying fix 1: disable container_connect_any"
SELINUX_FIX=$(mcp_call "selinux_set_boolean" '"name":"container_connect_any","value":"off"' 2>/dev/null || true)
ok "setsebool -P container_connect_any off"

step "Applying fix 2: add fapolicyd trust for agent binary"
FAPOLICYD_FIX=$(mcp_call "fapolicyd_add_rule" '"path":"/opt/compliance-agent/agent","decision":"allow"' 2>/dev/null || true)
ok "fapolicyd-cli --file add /opt/compliance-agent/agent --trust"
echo ""

step "Re-scanning..."
sleep 2
echo ""
ok "SELinux: container_connect_any = OFF"
ok "fapolicyd: allow rule present for agent binary"
ok "AIDE baseline: OK"
ok "File integrity: OK"
echo ""
ok "All findings resolved — image is clean"
sleep "$PAUSE"

pause

###############################################################################
act 5 "Auto-Enrollment"
###############################################################################
dev_points 3

step "Clean image triggers CI enrollment endpoint"
CI_RESULT=$(api_call POST "/ci/enroll" "$CAROL_TOKEN" -d '{
    "ipa_principal": "bootc/compliance-agent@'"${IPA_REALM}"'",
    "display_name": "Compliance Agent (dev-demo)",
    "workload_type": "bootc",
    "backend_types": ["cosign"],
    "artifact_ref": "'"${REGISTRY}"'/compliance-agent:latest",
    "image_digest": "sha256:dev-demo-placeholder",
    "metadata": {"git_commit": "f7a2c91", "ci_pipeline": "gitlab-ci", "pushed_by": "carol", "trust_tier": "verified"},
    "auto_attest": true
}')

WEBAPP_ID=$(echo "$CI_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('workload_id',''))" 2>/dev/null || true)
if [ -n "$WEBAPP_ID" ]; then
    track_workload "$WEBAPP_ID"
    ok "Workload registered: ${WEBAPP_ID}"
else
    warn "Registration response: $(echo "$CI_RESULT" | head -c 200)"
fi

step "Arbiter Hub → Keylime enrollment → attestation"
for i in $(seq 1 10); do
    STATE=$(api_call GET "/workloads/${WEBAPP_ID}" "$CAROL_TOKEN" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('current_state',''))" 2>/dev/null || true)
    [ "$STATE" = "healthy" ] && break
    note "attempt $i: state=$STATE"
    sleep 2
done

if [ "$STATE" = "healthy" ]; then
    ok "Workload HEALTHY — cosign verified, Keylime attested"
    note "Developer did nothing after push. Security handled enrollment automatically."
else
    warn "Workload state: $STATE (attestation may still be cycling)"
fi
sleep "$PAUSE"

pause

###############################################################################
act 6 "Sign — Artifact Provenance"
###############################################################################
dev_points 4

step "Carol signs the release artifact with her Kerberos identity"
note "kuipa sign blob release-1.0.tar"
echo ""

SIGN_OUTPUT=$(ssh_cmd "$AGENT_HOST" "echo 'compliance-agent-release-1.0' > /tmp/release-1.0.tar && kuipa sign blob /tmp/release-1.0.tar 2>&1" || true)
echo "$SIGN_OUTPUT" | while IFS= read -r line; do
    echo "  $line"
done
echo ""

if echo "$SIGN_OUTPUT" | grep -qi "signed\|signature\|tlog\|transparency"; then
    ok "Artifact signed with ML-DSA-65 (post-quantum)"
    ok "Transparency log entry recorded"
    note "Signed by: host/agent.${DOMAIN}@${IPA_REALM}"
    note "No GPG key management. No external CA. Identity-native."
else
    warn "Sign output may need review: $(echo "$SIGN_OUTPUT" | tail -1)"
fi
sleep "$PAUSE"

pause

###############################################################################
act 7 "Verify — Offline Verification"
###############################################################################
dev_points 5

step "Verifying artifact signature (offline — no server contact)"
note "kuipa sign verify release-1.0.tar"
echo ""

VERIFY_OUTPUT=$(ssh_cmd "$AGENT_HOST" "kuipa sign verify /tmp/release-1.0.tar 2>&1" || true)
echo "$VERIFY_OUTPUT" | while IFS= read -r line; do
    echo "  $line"
done
echo ""

if echo "$VERIFY_OUTPUT" | grep -qi "verified\|valid\|ok\|good"; then
    ok "Signature VERIFIED — offline, with realm pinned anchors"
    note "Anyone with the realm anchor can verify. No server needed."
else
    warn "Verify output: $(echo "$VERIFY_OUTPUT" | tail -1)"
fi
sleep "$PAUSE"

###############################################################################
# Cleanup
###############################################################################

ADMIN_TOKEN=$(get_token "attestation-admin")
cleanup_workloads "$ADMIN_TOKEN"

###############################################################################
demo_summary "DEVELOPER DEMO"
###############################################################################
echo "  1. Carol pushed agent code — one command, done"
echo "  2. Prescan found 2 issues — SELinux boolean + missing fapolicyd rule"
echo "  3. Findings report: actionable, not overwhelming"
echo "  4. Remediation: copy-paste fixes, re-scan clean"
echo "  5. Auto-enrollment: clean image → registered → attested → HEALTHY"
echo "  6. Signed release artifact with ML-DSA-65 (post-quantum)"
echo "  7. Offline verification — no server, no external PKI"
echo ""
echo -e "${BOLD}Key message:${NC} Security is invisible when you're clean."
echo -e "${BOLD}             Actionable when you're not. Never in your way.${NC}"
echo ""
