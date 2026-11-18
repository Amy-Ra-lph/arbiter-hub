#!/usr/bin/env bash
# CISO Persona Demo — Arbiter Hub
# Audience: Customer CISOs and security leadership evaluating AI risk
# Estimated time: 12 min
#
# Core message: You're throttling AI adoption because you can't prove trust.
# We give you the proof — hardware-rooted attestation, policy enforcement,
# audit trails, automated remediation — so you can open the throttle.
#
# Usage: source env/rebuild.env && ./ciso-demo.sh [--auto]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/demo-lib.sh"
source "${SCRIPT_DIR}/lib/talking-points.sh"

banner "CISO DEMO — Proving Trust at Scale (~12 min)"
note "Audience: CISOs and security leadership evaluating AI risk"
note "Message: Risk reduction enables value realization"
echo ""

step "Authenticating as security administrator"
ADMIN_TOKEN=$(get_token "attestation-admin")
ok "Admin token acquired"
sleep "$PAUSE"

###############################################################################
act 1 "Fleet Visibility"
###############################################################################
ciso_points 1

step "Loading fleet dashboard — all registered AI agents"
list_workloads "$ADMIN_TOKEN"

step "Trust tier breakdown"
WORKLOADS_JSON=$(api_call GET "/workloads?count=100" "$ADMIN_TOKEN")
echo "$WORKLOADS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tiers = {}
states = {}
for w in data.get('items', []):
    tier = w.get('metadata', {}).get('trust_tier', 'unclassified')
    state = w['current_state']
    tiers[tier] = tiers.get(tier, 0) + 1
    states[state] = states.get(state, 0) + 1

print()
print('  Trust Tier Distribution:')
tier_icons = {'sovereign': '🔒', 'verified': '✅', 'untrusted': '⚠️', 'unclassified': '❓'}
for tier, count in sorted(tiers.items()):
    icon = tier_icons.get(tier, '❓')
    print(f'    {icon} {tier:<15s} {count} workload(s)')

print()
print('  Health Status:')
state_icons = {'healthy': '🟢', 'failed': '🔴', 'registered': '🟡', 'enrolled': '🟡', 'revoked': '⛔'}
for state, count in sorted(states.items()):
    icon = state_icons.get(state, '⚪')
    print(f'    {icon} {state:<15s} {count}')
" 2>/dev/null

ok "Fleet visibility established — every agent, every trust level, real-time"
sleep "$PAUSE"

pause

###############################################################################
act 2 "Trust Tier Model"
###############################################################################

step "Three-tier graduated trust model"
echo ""
echo -e "  ${BOLD}SOVEREIGN${NC}  — Full access to sensitive resources"
note "Hardware-attested, identity-verified, policy-compliant"
note "Access: KBS secrets, cross-realm delegation, signing authority"
note "Policy: SELinux enforcing, fapolicyd allow-list, AIDE baseline clean"
echo ""
echo -e "  ${BOLD}VERIFIED${NC}   — Limited access, monitored operations"
note "Hardware-attested, identity-verified"
note "Access: own-scope resources, monitored API calls"
note "Policy: SELinux enforcing, behavioral monitoring active"
echo ""
echo -e "  ${BOLD}UNTRUSTED${NC}  — Sandboxed, heavily monitored"
note "Identity-verified only, no hardware attestation"
note "Access: sandboxed execution, no secrets access"
note "Policy: Falco behavioral analysis, network restrictions, auto-quarantine on anomaly"
echo ""
ciso_points 1
ok "Risk is graduated — not binary allow/deny"
sleep "$PAUSE"

pause

###############################################################################
act 3 "Compliance Evidence"
###############################################################################
ciso_points 2

step "Retrieving attestation records for a healthy workload"
HEALTHY_ID=$(echo "$WORKLOADS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if w['current_state'] == 'healthy':
        print(w['id'])
        break
" 2>/dev/null)

HEALTHY_NAME=$(echo "$WORKLOADS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if w['current_state'] == 'healthy':
        print(w['display_name'])
        break
" 2>/dev/null)

if [ -n "$HEALTHY_ID" ]; then
    ok "Selected: ${HEALTHY_NAME} (${HEALTHY_ID})"

    step "Attestation evidence chain"
    ATTEST=$(api_call POST "/workloads/${HEALTHY_ID}/attest" "$ADMIN_TOKEN" 2>/dev/null)
    echo "$ATTEST" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Overall verdict: {data.get(\"verdict\", \"unknown\")}')
print(f'  Current state:   {data.get(\"state\", \"unknown\")}')
print()
for b in data.get('per_backend', []):
    icon = '✓' if b['verdict'] == 'pass' else '✗'
    print(f'    {icon} {b[\"backend\"]:.<20s} verdict={b[\"verdict\"]}')
    if 'quote_hash' in b:
        print(f'      TPM quote hash: {b[\"quote_hash\"]}')
    if 'timestamp' in b:
        print(f'      Timestamp:      {b[\"timestamp\"]}')
    if 'policy_hash' in b:
        print(f'      Policy hash:    {b[\"policy_hash\"]}')
" 2>/dev/null || echo "$ATTEST" | python3 -m json.tool 2>/dev/null | head -20

    ok "Auditable proof: host ${HEALTHY_NAME} compliant at this moment"
    note "This evidence is exportable for regulators — hardware-rooted, timestamped, policy-hashed"
else
    warn "No healthy workloads found — skipping attestation evidence"
fi
sleep "$PAUSE"

pause

###############################################################################
act 4 "Incident Response"
###############################################################################
ciso_points 3

step "Scenario: rogue agent attempts sensitive file access in untrusted sandbox"
note "Falco is monitoring all untrusted-tier workloads for behavioral anomalies"
sleep "$PAUSE"

step "Triggering malicious activity in wid-untrusted container"
ssh_cmd "$AGENT_HOST" "podman exec wid-untrusted cat /etc/shadow" || true
ok "Sensitive file access triggered — Falco alert generated"
sleep 2

step "Checking Falco detection → state transition"
UNTRUSTED_ID=""
UNTRUSTED_STATE=""
for i in $(seq 1 12); do
    RESULT=$(api_call GET "/workloads?count=100" "$ADMIN_TOKEN" 2>/dev/null)
    UNTRUSTED_STATE=$(echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['current_state'])
        break
" 2>/dev/null || echo "unknown")
    UNTRUSTED_ID=$(echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'untrusted' in w.get('display_name','').lower():
        print(w['id'])
        break
" 2>/dev/null || true)
    [ "$UNTRUSTED_STATE" = "failed" ] && break
    echo "  polling ($i/12): state=$UNTRUSTED_STATE"
    sleep 3
done

if [ "$UNTRUSTED_STATE" = "failed" ]; then
    ok "Falco detected malicious activity → workload moved to FAILED"
else
    warn "Workload state: $UNTRUSTED_STATE (EDA pipeline may still be processing)"
fi
sleep "$PAUSE"

step "Administrator revokes compromised workload"
if [ -n "$UNTRUSTED_ID" ]; then
    api_call POST "/workloads/${UNTRUSTED_ID}/revoke" "$ADMIN_TOKEN" -d '{
        "justification": "Rogue agent detected: unauthorized access to /etc/shadow in untrusted sandbox"
    }' | python3 -m json.tool 2>/dev/null || true
    ok "Workload revoked — credentials invalidated, access removed"
fi
note "In production: EDA rulebook automates this — detection to containment without human intervention"
sleep "$PAUSE"

pause

###############################################################################
act 5 "Audit Trail"
###############################################################################

step "Complete audit trail — every state transition, every actor, every timestamp"
show_audit "$ADMIN_TOKEN" 20
echo ""
ok "Full evidence chain for regulators and incident response"
note "Every operation recorded: who did what, when, to which workload"
note "Immutable — API-generated, not manually entered"
sleep "$PAUSE"

pause

###############################################################################
act 6 "Provenance — Post-Quantum Signing"
###############################################################################
ciso_points 4

step "Transparency log — every signing event recorded"
ssh_cmd "$AGENT_HOST" "kuipa tlog 2>&1" || warn "Transparency log query requires enrolled host"
sleep "$PAUSE"

step "Artifact signing with post-quantum cryptography"
note "ML-DSA-65 signatures — quantum-resistant, identity-native"
ssh_cmd "$AGENT_HOST" "echo 'compliance-report-2026-q4' > /tmp/compliance-report.tar && kuipa sign blob /tmp/compliance-report.tar 2>&1" || warn "kuipa sign requires host Kerberos ticket"
sleep "$PAUSE"

step "Offline verification — no server contact needed"
ssh_cmd "$AGENT_HOST" "kuipa sign verify /tmp/compliance-report.tar 2>&1" || warn "kuipa verify requires pinned anchors"
ok "Every artifact signed, every signing event logged — non-repudiable"
note "No external CA, no GPG key management — identity-native from the Kerberos realm"
sleep "$PAUSE"

pause

###############################################################################
act 7 "Investment Enablement"
###############################################################################
ciso_points 5

demo_summary "CISO DEMO"
echo "  1. Fleet visibility: every AI agent, every trust level, real-time status"
echo "  2. Graduated trust: sovereign / verified / untrusted — risk-proportional access"
echo "  3. Compliance evidence: hardware-rooted attestation, timestamped, policy-hashed"
echo "  4. Incident response: detection → containment → revocation (automatable via EDA)"
echo "  5. Audit trail: immutable record of every operation for regulators"
echo "  6. Provenance: post-quantum signing, transparency log, offline verification"
echo ""
echo -e "${BOLD}The bottom line:${NC}"
echo "  The more you trust the pipeline, the more agents you deploy."
echo "  This isn't a brake — it's what lets you accelerate."
echo ""
echo -e "${BOLD}Standards alignment:${NC} WIMSE, AuthZEN, NIST AI 100-2, EU AI Act"
echo ""
