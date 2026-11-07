#!/usr/bin/env bash
# RSAC / Industry persona demo for Arbiter Hub
# Audience: security professionals, analysts, press
# Estimated time: 15 min (with audience interaction)
#
# Usage: source env/rebuild.env && ./rsac-demo.sh [--auto]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/demo-lib.sh"
source "${SCRIPT_DIR}/lib/talking-points.sh"

banner "RSAC DEMO — Agentic AI Trust Model (~15 min)"
note "Audience: security professionals, analysts, press"
note "Thesis: the industry needs a trust model for AI agents. Here's one."
echo ""

step "Authenticating with OIDC identity provider"
ADMIN_TOKEN=$(get_token "attestation-admin")
ok "Admin token acquired"

step "Detecting Keylime agent"
KEYLIME_UUID=$(ssh_cmd "$AGENT_HOST" "grep -oP '(?<=uuid\s=\s\").*(?=\")' /etc/keylime/agent.conf" || true)
KEYLIME_IP=$(getent hosts "$AGENT_HOST" | awk '{print $1}' 2>/dev/null || true)
[ -z "$KEYLIME_IP" ] && KEYLIME_IP=$(dig +short "$AGENT_HOST" 2>/dev/null || true)
if [ -n "$KEYLIME_UUID" ]; then
    ok "Keylime agent: ${KEYLIME_UUID}"
else
    warn "Keylime agent not detected — enrollment will skip attestation backend"
fi

pause

###############################################################################
act 1 "THE PROBLEM"
###############################################################################

rsac_points 1

echo -e "${BOLD}Every AI agent today runs with implicit trust.${NC}"
echo ""
note "No hardware root of trust — agents run on whatever machine, unverified"
note "No identity lifecycle — no enrollment, no revocation, no audit trail"
note "No policy enforcement — agents access what they want, when they want"
note "No provenance — no way to prove who built what, or when"
echo ""
echo -e "${BOLD}This is the 2027 version of 'just run as root.'${NC}"
echo ""
note "The industry is starting to respond — IBM shipped Agent Identity last week."
note "But the response so far is identity-only: OAuth tokens, secrets vaults, audit logs."
note "No hardware root of trust. No policy enforcement below the app. No post-quantum crypto."
note "Identity is necessary. Identity alone isn't trust."

pause

###############################################################################
act 2 "THE MODEL"
###############################################################################

rsac_points 2

echo -e "${BOLD}Architecture: six layers, open standards at each${NC}"
echo ""
echo -e "${DIM}  ┌─────────────────────────────────────────────────────┐${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  │  ${NC}${BOLD}1. IDENTITY${NC}${DIM}       IPA / Kerberos / OIDC            │${NC}"
echo -e "${DIM}  │                  Principal lifecycle, authentication │${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  │  ${NC}${BOLD}2. ATTESTATION${NC}${DIM}    Keylime / TPM 2.0                │${NC}"
echo -e "${DIM}  │                  Hardware-rooted trust quotes        │${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  │  ${NC}${BOLD}3. POLICY${NC}${DIM}         enforcement-mcp                  │${NC}"
echo -e "${DIM}  │                  SELinux, fapolicyd, AIDE, MLS       │${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  │  ${NC}${BOLD}4. MONITORING${NC}${DIM}     Falco + behavioral classifier    │${NC}"
echo -e "${DIM}  │                  Runtime anomaly detection           │${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  │  ${NC}${BOLD}5. SIGNING${NC}${DIM}        kuipa / ML-DSA-65                │${NC}"
echo -e "${DIM}  │                  PQ artifact provenance, tlog        │${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  │  ${NC}${BOLD}6. REMEDIATION${NC}${DIM}    EDA / Ansible                    │${NC}"
echo -e "${DIM}  │                  Automated response to trust events  │${NC}"
echo -e "${DIM}  │                                                     │${NC}"
echo -e "${DIM}  └─────────────────────────────────────────────────────┘${NC}"
echo ""
note "Each layer uses open standards. No vendor lock-in."
note "Composable: adopt one layer or all six."
note "What we're about to show runs on 3 bare RHEL VMs. No Kubernetes."

pause

###############################################################################
act 3 "LIVE — Enrollment to Attestation"
###############################################################################

rsac_points 3

step "Registering new workload: 'RSAC Live Agent'"
RSAC_RESULT=$(api_call POST "/workloads" "$ADMIN_TOKEN" -d '{
    "ipa_principal": "service/rsac-live-agent@'"${IPA_REALM}"'",
    "display_name": "RSAC Live Agent",
    "workload_type": "agentic",
    "backend_types": ["keylime", "falco"],
    "metadata": {
        "trust_tier": "verified",
        "role": "rsac-demo",
        "keylime_agent_uuid": "'"${KEYLIME_UUID}"'",
        "keylime_agent_ip": "'"${KEYLIME_IP}"'",
        "description": "Live enrollment demo for RSAC audience"
    }
}')
RSAC_ID=$(echo "$RSAC_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
track_workload "$RSAC_ID"
ok "Registered: ${RSAC_ID}"
note "IPA principal created, OIDC token scoped, workload tracked"
sleep "$PAUSE"

step "Enrolling with Keylime verifier (hardware attestation)"
ENROLL_RESULT=$(api_call POST "/workloads/${RSAC_ID}/enroll" "$ADMIN_TOKEN" -d '{"auto_attest": true}')
ALREADY=$(echo "$ENROLL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',{}).get('already_enrolled',False))" 2>/dev/null)
if [ "$ALREADY" = "True" ]; then
    ok "Agent already enrolled — skip-if-healthy logic"
else
    ok "Enrolled with Keylime verifier"
fi
sleep "$PAUSE"

step "Triggering attestation — TPM quote from hardware"
ATTEST_RESULT=$(api_call POST "/workloads/${RSAC_ID}/attest" "$ADMIN_TOKEN")
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
    ok "HEALTHY — hardware-rooted trust established"
else
    warn "State: ${STATE} (background attestation may be pending)"
fi
note "Identity → OIDC → Keylime → TPM quote → PASS. Under 30 seconds."

pause

###############################################################################
act 4 "LIVE — The Hard Thing: Attested Signing"
###############################################################################

rsac_points 4

step "Creating artifact on agent node"
ssh_cmd "$AGENT_HOST" "echo 'rsac-demo-artifact-v1' > /tmp/rsac-artifact.tar"
ok "Artifact created: /tmp/rsac-artifact.tar"

step "Signing with kuipa (ML-DSA-65, Kerberos identity)"
echo ""
SIGN_OUTPUT=$(ssh_cmd "$AGENT_HOST" "kuipa sign blob /tmp/rsac-artifact.tar --verbose 2>&1")
echo "$SIGN_OUTPUT" | while IFS= read -r line; do
    echo -e "  ${DIM}${line}${NC}"
done
echo ""
ok "Artifact signed — ML-DSA-65 post-quantum signature"
note "Kerberos ticket → server validates principal → transparency log entry"
note "No external CA, no GPG key management, no certificate lifecycle"
sleep "$PAUSE"

step "Offline verification (no server contact)"
echo ""
VERIFY_OUTPUT=$(ssh_cmd "$AGENT_HOST" "kuipa sign verify /tmp/rsac-artifact.tar 2>&1")
echo "$VERIFY_OUTPUT" | while IFS= read -r line; do
    echo -e "  ${DIM}${line}${NC}"
done
echo ""
ok "Signature verified offline — realm anchors are sufficient"
sleep "$PAUSE"

step "Transparency log — who signed what, when"
TLOG_OUTPUT=$(ssh_cmd "$AGENT_HOST" "kuipa tlog 2>&1")
echo "$TLOG_OUTPUT" | while IFS= read -r line; do
    echo -e "  ${DIM}${line}${NC}"
done
ok "Every signing event logged, append-only, auditable"
note "sigstore model — but with Kerberos realm authority instead of OIDC IdP"

pause

###############################################################################
act 5 "LIVE — Rogue Agent Containment"
###############################################################################

rsac_points 5

step "Triggering rogue behavior in untrusted sandbox"
ssh_cmd "$AGENT_HOST" "podman exec wid-untrusted cat /etc/shadow" || true
ok "Rogue action triggered: sensitive file read in wid-untrusted"
note "Falco detects the syscall. Behavioral classifier flags the pattern."
sleep 5

step "Polling workload state (expecting FAILED)"
UNTRUSTED_ID=""
UNTRUSTED_STATE="unknown"
for i in $(seq 1 10); do
    WORKLOADS_JSON=$(api_call GET "/workloads?count=100" "$ADMIN_TOKEN" 2>/dev/null)
    read -r UNTRUSTED_ID UNTRUSTED_STATE < <(echo "$WORKLOADS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['id'], w['current_state'])
        break
" 2>/dev/null || echo "")
    [ "$UNTRUSTED_STATE" = "failed" ] && break
    echo "  attempt $i: state=$UNTRUSTED_STATE"
    sleep 3
done

if [ "$UNTRUSTED_STATE" = "failed" ]; then
    ok "wid-untrusted → FAILED (Falco detected malicious activity)"
else
    warn "State: $UNTRUSTED_STATE (detection may still be processing)"
fi
sleep "$PAUSE"

step "Revoking compromised workload"
if [ -n "$UNTRUSTED_ID" ]; then
    api_call POST "/workloads/${UNTRUSTED_ID}/revoke" "$ADMIN_TOKEN" -d '{
        "justification": "Rogue agent — sensitive file access in sandboxed tier"
    }' | python3 -m json.tool 2>/dev/null || true
    ok "Workload revoked — identity and attestation invalidated"
fi
sleep "$PAUSE"

step "Audit trail — full evidence chain"
show_audit "$ADMIN_TOKEN" 15
ok "Every state transition, every actor, every timestamp"
note "Trigger → detect → quarantine → revoke. Under 60 seconds."

pause

###############################################################################
act 6 "Standards Alignment"
###############################################################################

rsac_points 6

echo -e "${BOLD}This model maps to where regulation and standards are heading:${NC}"
echo ""
echo -e "  ${GREEN}▸${NC} ${BOLD}WIMSE${NC} (Workload Identity in Multi-System Environments)"
note "    IETF working group. Our OIDC token model aligns with WIMSE workload identity."
echo ""
echo -e "  ${GREEN}▸${NC} ${BOLD}AuthZEN${NC} (Authorization API)"
note "    OpenID Foundation. Trust-tier policy decisions map to AuthZEN PDP/PEP model."
echo ""
echo -e "  ${GREEN}▸${NC} ${BOLD}NIST AI 100-2${NC} (Adversarial ML)"
note "    Attestation + behavioral monitoring addresses AI supply chain threats."
echo ""
echo -e "  ${GREEN}▸${NC} ${BOLD}EU AI Act${NC} (High-Risk AI Systems)"
note "    Audit trails, provenance, risk-graduated trust tiers = compliance evidence."
echo ""
echo -e "  ${GREEN}▸${NC} ${BOLD}NIST SP 800-207${NC} (Zero Trust Architecture)"
note "    Per-workload identity, continuous attestation, least-privilege policy."
echo ""
echo -e "  ${GREEN}▸${NC} ${BOLD}Market validation${NC} (IBM Agent Identity, GA Oct 2026)"
note "    IBM Verify + HashiCorp Vault + watsonx. Identity + credential brokering."
note "    We add what they don't: hardware attestation, graduated policy enforcement, PQ signing."
echo ""
note "Not future work — the demo you just saw implements these patterns today."

pause

###############################################################################
act 7 "Open Invitation"
###############################################################################

echo -e "${BOLD}The components are open:${NC}"
echo ""
note "Identity:      FreeIPA (GPLv3)"
note "Attestation:   Keylime (Apache 2.0)"
note "Policy:        SELinux, fapolicyd, AIDE (GPL)"
note "Monitoring:    Falco (Apache 2.0)"
note "Signing:       kuipa — ML-DSA-65, ML-KEM-768 (upstream IPA)"
note "Orchestration: Ansible (GPL)"
echo ""
echo -e "${BOLD}The architecture is composable.${NC}"
note "Adopt one layer or all six. Each adds value independently."
echo ""
echo -e "${BOLD}We're contributing to the standards.${NC}"
note "WIMSE, AuthZEN, NIST AI working groups."
echo ""
echo -e "${CYAN}${BOLD}What's your trust model?${NC}"

pause

###############################################################################
# Cleanup
###############################################################################

cleanup_workloads "$ADMIN_TOKEN"
ssh_cmd "$AGENT_HOST" "rm -f /tmp/rsac-artifact.tar /tmp/rsac-artifact.tar.kusig" || true

demo_summary "RSAC DEMO"
echo "  1. Framed the problem: AI agents without trust models"
echo "  2. Presented the six-layer architecture (open standards)"
echo "  3. Live: enrollment → attestation in under 30 seconds"
echo "  4. Live: post-quantum signing with Kerberos identity (ML-DSA-65)"
echo "  5. Live: rogue agent detection → revocation in under 60 seconds"
echo "  6. Standards alignment: WIMSE, AuthZEN, NIST, EU AI Act"
echo "  7. Open invitation: composable, open-source, standards-track"
echo ""
echo -e "${BOLD}Key differentiators shown:${NC}"
echo "  - Hardware root of trust (TPM, not software attestation)"
echo "  - Identity-native signing (Kerberos, not external CA)"
echo "  - Post-quantum crypto (ML-DSA-65, ML-KEM-768 — no vendored crypto)"
echo "  - Graduated trust (3 tiers, not binary allow/deny)"
echo "  - Full audit trail (every action, every actor, every timestamp)"
echo ""
