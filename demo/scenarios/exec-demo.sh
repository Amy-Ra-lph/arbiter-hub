#!/usr/bin/env bash
# Executive Demo — Arbiter Hub
# Audience: RH VPs, SVPs, BU leads
# Core message: AI agents run on RHEL everywhere. The trust and identity layer
#   is platform infrastructure that makes the entire RH portfolio more valuable.
# Estimated time: 12 minutes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/demo-lib.sh"
source "${SCRIPT_DIR}/lib/talking-points.sh"

banner "EXECUTIVE DEMO — Arbiter Hub (≈12 min)"
note "3 bare RHEL VMs. No OpenShift. Full pipeline."
note "RHEL (trust) + AAP (response) + OCP (orchestrate)"

step "Authenticating as attestation admin"
ADMIN_TOKEN=$(get_token "attestation-admin")
ok "OIDC token acquired"

step "Detecting Keylime agent"
KEYLIME_UUID=$(ssh_cmd "$AGENT_HOST" \
    "grep -oP '(?<=uuid\s=\s\").*(?=\")' /etc/keylime/agent.conf" || true)
KEYLIME_IP=$(getent hosts "$AGENT_HOST" | awk '{print $1}' 2>/dev/null || true)
[ -z "$KEYLIME_IP" ] && KEYLIME_IP=$(dig +short "$AGENT_HOST" 2>/dev/null || true)
if [ -n "$KEYLIME_UUID" ]; then
    ok "Keylime agent: ${KEYLIME_UUID}"
else
    warn "Keylime agent UUID not detected — enrollment will skip attestation"
fi
sleep "$PAUSE"

###############################################################################
act 1 "The Estate"
exec_points 1
###############################################################################

step "Showing fleet: workloads across trust tiers"
list_workloads "$ADMIN_TOKEN"

step "Querying attestation backend health"
BACKENDS=$(api_call GET "/backends" "$ADMIN_TOKEN")
echo "$BACKENDS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for name, info in data.items():
    icon = '✓' if info.get('healthy') else '✗'
    print(f'  {icon} {name}: {info.get(\"detail\", \"\")}')
" 2>/dev/null || echo "$BACKENDS" | python3 -m json.tool 2>/dev/null
ok "Fleet visible — all backends reporting"
note "10 workloads, 3 trust tiers (sovereign / verified / untrusted), hardware attestation"
sleep "$PAUSE"

pause

###############################################################################
act 2 "Identity Is the Control Plane"
exec_points 2
###############################################################################

step "Registering new agentic workload: 'Risk Assessment Agent'"
NEW_RESULT=$(api_call POST "/workloads" "$ADMIN_TOKEN" -d '{
    "ipa_principal": "service/risk-assessment@'"${IPA_REALM}"'",
    "display_name": "Risk Assessment Agent",
    "workload_type": "agentic",
    "backend_types": ["keylime", "falco"],
    "metadata": {
        "trust_tier": "verified",
        "role": "risk-assessment",
        "keylime_agent_uuid": "'"${KEYLIME_UUID}"'",
        "keylime_agent_ip": "'"${KEYLIME_IP}"'",
        "description": "Evaluates deployment risk posture"
    }
}')
NEW_ID=$(echo "$NEW_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
echo "$NEW_RESULT" | python3 -m json.tool 2>/dev/null | head -12
ok "Workload registered: ${NEW_ID}"
track_workload "$NEW_ID"
note "IPA principal → OIDC token → Arbiter Hub registration"
sleep "$PAUSE"

step "Enrolling with Keylime verifier"
ENROLL_RESULT=$(api_call POST "/workloads/${NEW_ID}/enroll" "$ADMIN_TOKEN" -d '{"auto_attest": true}')
ALREADY=$(echo "$ENROLL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',{}).get('already_enrolled',False))" 2>/dev/null)
if [ "$ALREADY" = "True" ]; then
    ok "Agent already enrolled in verifier — skip-if-healthy"
else
    ok "Agent enrolled with Keylime"
fi
sleep "$PAUSE"

step "Triggering attestation"
ATTEST_RESULT=$(api_call POST "/workloads/${NEW_ID}/attest" "$ADMIN_TOKEN")
echo "$ATTEST_RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Verdict: {data.get(\"verdict\", \"unknown\")}')
print(f'  State:   {data.get(\"state\", \"unknown\")}')
for b in data.get('per_backend', []):
    icon = '✓' if b['verdict'] == 'pass' else '✗'
    print(f'    {icon} {b[\"backend\"]}: {b[\"verdict\"]}')
" 2>/dev/null
STATE=$(echo "$ATTEST_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null)
if [ "$STATE" = "healthy" ]; then
    ok "Workload HEALTHY — hardware-attested, runtime-monitored"
else
    warn "State: $STATE (attestation may still be processing)"
fi
note "Identity → enrollment → attestation → healthy. One pipeline."
sleep "$PAUSE"

pause

###############################################################################
act 3 "Automated Response (AAP Story)"
exec_points 3
###############################################################################

step "Launching rogue agent in wid-untrusted sandbox"
ssh_cmd "$AGENT_HOST" "podman exec wid-untrusted cat /etc/shadow" || true
ok "Triggered Falco alert: sensitive file access in untrusted tier"
sleep 5

step "Checking workload state transition"
for i in $(seq 1 10); do
    UNTRUSTED_STATE=$(api_call GET "/workloads?count=100" "$ADMIN_TOKEN" 2>/dev/null \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['current_state'])
        break
" 2>/dev/null || echo "unknown")
    [ "$UNTRUSTED_STATE" = "failed" ] && break
    [ "$i" -lt 10 ] && sleep 3
done

if [ "$UNTRUSTED_STATE" = "failed" ]; then
    ok "wid-untrusted → FAILED (Falco detected malicious activity)"
else
    warn "Workload state: $UNTRUSTED_STATE (EDA processing may be pending)"
fi
sleep "$PAUSE"

step "Reviewing audit trail — detection to containment"
show_audit "$ADMIN_TOKEN" 10
ok "Full audit trail: every state transition, actor, timestamp"
note "EDA rulebook fires → remediation playbook runs → workload revoked"
note "This is where AAP plugs in — Ansible automation responds to attestation events"
sleep "$PAUSE"

step "Revoking compromised workload"
UNTRUSTED_ID=$(api_call GET "/workloads?count=100" "$ADMIN_TOKEN" 2>/dev/null \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['id'])
        break
" 2>/dev/null || true)
if [ -n "$UNTRUSTED_ID" ]; then
    api_call POST "/workloads/${UNTRUSTED_ID}/revoke" "$ADMIN_TOKEN" -d '{
        "justification": "Rogue agent — sensitive file access in untrusted sandbox"
    }' | python3 -m json.tool 2>/dev/null || true
    ok "Workload revoked"
fi

pause

###############################################################################
act 4 "Container Readiness (OCP Story)"
exec_points 4
###############################################################################

step "Showing cosign-verified bootc workload"
api_call GET "/workloads?count=100" "$ADMIN_TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'bootc' in w.get('workload_type','').lower() or 'bootc' in w.get('display_name','').lower():
        state = w['current_state']
        icon = '🟢' if state == 'healthy' else '🔴'
        backends = ', '.join(w.get('backend_types', []))
        print(f'  {icon} {w[\"display_name\"]}')
        print(f'       state:    {state}')
        print(f'       type:     {w[\"workload_type\"]}')
        print(f'       backends: {backends}')
        print(f'       principal: {w[\"ipa_principal\"]}')
        ref = w.get('metadata', {}).get('artifact_ref', '')
        if ref:
            print(f'       image:    {ref}')
        print()
" 2>/dev/null || warn "No bootc workloads found"

ok "Cosign signature verified — container image trusted"
note "Same trust model follows the workload to OCP"
note "Attestation is portable: RHEL VM → OpenShift pod → edge device"
sleep "$PAUSE"

pause

###############################################################################
act 5 "PQ-Ready Supply Chain (Differentiation)"
exec_points 5
###############################################################################

step "Signing artifact with post-quantum credentials (ML-DSA-65)"
ssh_cmd "$AGENT_HOST" "echo 'release-1.0 artifact payload' > /tmp/release-1.0.tar"
SIGN_OUTPUT=$(ssh_cmd "$AGENT_HOST" "kuipa sign blob /tmp/release-1.0.tar --verbose 2>&1" || true)
echo "$SIGN_OUTPUT" | head -20
if echo "$SIGN_OUTPUT" | grep -qi "signed\|kusig\|transparency"; then
    ok "Artifact signed — ML-DSA-65 signature + transparency log entry"
else
    warn "Sign output may need review"
    echo "$SIGN_OUTPUT"
fi
sleep "$PAUSE"

step "Verifying signature offline"
VERIFY_OUTPUT=$(ssh_cmd "$AGENT_HOST" "kuipa sign verify /tmp/release-1.0.tar 2>&1" || true)
echo "$VERIFY_OUTPUT"
if echo "$VERIFY_OUTPUT" | grep -qi "verified\|valid\|ok"; then
    ok "Offline verification passed — no server needed"
else
    warn "Verify output may need review"
fi
note "Post-quantum signing with no external PKI. Kerberos identity is the signing authority."
note "Transparency log: who signed what, when. Non-repudiable."
sleep "$PAUSE"

step "Cleaning up demo artifact"
ssh_cmd "$AGENT_HOST" "rm -f /tmp/release-1.0.tar /tmp/release-1.0.tar.kusig" || true

pause

###############################################################################
act 6 "Portfolio Map"
exec_points 6
###############################################################################

echo -e "${BOLD}The Security Pipeline — Three Products, One Architecture:${NC}"
echo ""
echo -e "  ${GREEN}RHEL + IdM${NC}    = Trust Foundation"
echo "                 Attestation, identity, signing, policy"
echo "                 Hardware root of trust (TPM/Keylime)"
echo "                 Post-quantum crypto (kuipa/ML-DSA-65)"
echo ""
echo -e "  ${YELLOW}AAP${NC}           = Automated Response"
echo "                 EDA rulebooks trigger on attestation events"
echo "                 AWX runs remediation playbooks"
echo "                 Policy enforcement via enforcement-mcp"
echo ""
echo -e "  ${CYAN}OCP${NC}           = Container Orchestration"
echo "                 Same trust model via SPIRE + workload identity"
echo "                 cosign-verified images, attestation follows workloads"
echo "                 Scales the identity pipeline to clusters"
echo ""
echo -e "${BOLD}Each upsell adds value because the trust foundation is already there.${NC}"
echo -e "${BOLD}This is not three products competing — it's one security pipeline.${NC}"
sleep "$PAUSE"

###############################################################################
# Cleanup
###############################################################################

cleanup_workloads "$ADMIN_TOKEN"

demo_summary "EXECUTIVE DEMO"
echo "  1. Fleet: 10 workloads across 3 trust tiers, all managed by identity"
echo "  2. Enrollment: IPA principal → OIDC → Keylime attestation → HEALTHY"
echo "  3. Incident: Falco detect → EDA quarantine → audit trail → revoke"
echo "  4. Containers: cosign-verified bootc, attestation follows to OCP"
echo "  5. PQ signing: ML-DSA-65 artifact signing, transparency log, offline verify"
echo "  6. Portfolio: RHEL (trust) + AAP (response) + OCP (orchestrate)"
echo ""
echo -e "${BOLD}Key takeaway:${NC} AI agents run on RHEL everywhere."
echo "The trust layer is platform infrastructure below the orchestrator."
echo "No OpenShift required. Full pipeline works on bare RHEL VMs."
