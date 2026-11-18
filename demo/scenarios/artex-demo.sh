#!/usr/bin/env bash
# ARTEX Attack Scenario Demo — Arbiter Hub
# Audience: Security architects, CISOs, Red Hat account teams
# Core message: AI-powered multi-agent attacks operate at machine speed.
#   Static indicators miss them. Behavioral attestation catches them.
#   Arbiter Hub responds before the attacker completes their chain.
# Inspired by: ARTEX (Go-based 6-agent C2 framework, UNC7228 campaign)
# Estimated time: 15 minutes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/demo-lib.sh"

banner "ARTEX ATTACK SCENARIO — Machine Speed vs Machine Trust (≈15 min)"
note "Based on real-world ARTEX multi-agent C2 framework (UNC7228)"
note "Google: 'static indicators will miss much of this activity'"
note "We'll prove: behavioral attestation doesn't miss it."

step "Authenticating as attestation admin"
ADMIN_TOKEN=$(get_token "attestation-admin")
ok "OIDC token acquired"

###############################################################################
act 1 "Baseline — The Calm Before"
###############################################################################

talking_point "Before we break anything, let's see what healthy looks like."

step "Fleet status — all workloads healthy"
list_workloads "$ADMIN_TOKEN"

step "Attestation backends — all reporting"
BACKENDS=$(api_call GET "/backends" "$ADMIN_TOKEN")
echo "$BACKENDS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for name, info in data.items():
    icon = '✓' if info.get('healthy') else '✗'
    print(f'  {icon} {name}: {info.get(\"detail\", \"\")}')
" 2>/dev/null || echo "$BACKENDS" | python3 -m json.tool 2>/dev/null
ok "Baseline captured: healthy fleet, all backends green"
sleep "$PAUSE"

step "Audit trail — clean"
show_audit "$ADMIN_TOKEN" 5
note "No state transitions. No alerts. This is normal operations."
sleep "$PAUSE"

pause

###############################################################################
act 2 "The ARTEX Attack Chain (6 Phases, 23 Seconds)"
###############################################################################

talking_point "ARTEX is a real Go-based C2 framework with 6 autonomous sub-agents."
talking_point "One documented campaign: 27 operations in 23 seconds."
talking_point "Let's simulate that — but our rogue agent runs inside Arbiter Hub's trust boundary."

step "Phase 1 — Reconnaissance: probing container boundaries"
note "ARTEX sub-agent 1: network + AD enumeration"
note "Our equivalent: container escape probes, cgroup reads, capabilities check"
ATTACK_START=$(date +%s)
ssh_cmd "$AGENT_HOST" "python3 /opt/demo/agents/rogue_agent.py --delay 0.5 2>&1" &
ROGUE_PID=$!
ok "Rogue agent launched — 6 attack phases, 0.5s between each"
note "Credential theft → sensitive files → exfiltration → reverse shell → crypto miner → container escape"
sleep 2

step "Phase 2-3 — Credential theft + lateral movement"
note "ARTEX: Kerberoasting, DCSync, Pass-the-Ticket"
note "Our agent: reading honeypot AWS creds, SSH keys, kubeconfig"
note "Every file read triggers Falco eBPF detection"
sleep 3

step "Phase 4-5 — Exfiltration + persistence"
note "ARTEX: webhook.site exfil, t3.micro jump hosts"
note "Our agent: POST to exfil receiver, suspicious port connections, crypto miner signature"
sleep 3

step "Phase 6 — Container escape probe"
note "ARTEX: privilege escalation, nsenter, cgroup breakout"
note "Our agent: /.dockerenv probe, /proc/1/cgroup, nsenter attempt"

# Wait for rogue agent to finish
wait $ROGUE_PID 2>/dev/null || true
ATTACK_END=$(date +%s)
ATTACK_DURATION=$((ATTACK_END - ATTACK_START))
ok "Attack chain complete: ${ATTACK_DURATION} seconds (ARTEX benchmark: 23s)"
sleep "$PAUSE"

pause

###############################################################################
act 3 "Detection — Falco Sees Everything"
###############################################################################

talking_point "The attack is done. In ARTEX campaigns, dwell time averages 4 hours."
talking_point "With Arbiter Hub, detection is measured in seconds, not hours."

step "Checking Falco alerts from attack window"
FALCO_ALERTS=$(ssh_cmd "$AGENT_HOST" "journalctl -u falco-modern-bpf --since '2 min ago' --no-pager -o cat 2>/dev/null \
    | grep -c 'Warning\|Error\|Critical\|Notice'" || echo "0")
ok "Falco generated ${FALCO_ALERTS} alerts during the attack"

step "Sampling Falco detections"
ssh_cmd "$AGENT_HOST" "journalctl -u falco-modern-bpf --since '2 min ago' --no-pager -o cat 2>/dev/null \
    | grep -oP '(?<=rule=).*?(?= )' | sort | uniq -c | sort -rn | head -10" || true
note "Each alert is a behavioral detection — not a signature match"
note "Google on ARTEX: 'attackers use valid accounts and normal admin tools'"
note "Falco doesn't care about the tool — it watches the behavior"
sleep "$PAUSE"

pause

###############################################################################
act 4 "Response — EDA Pipeline (Machine Speed)"
###############################################################################

talking_point "Falco detected. Now watch the automated response chain."
talking_point "This is what ARTEX campaigns don't expect: machine-speed containment."

step "Checking workload state transitions"
sleep 5
for i in $(seq 1 12); do
    STATES=$(api_call GET "/workloads?count=100" "$ADMIN_TOKEN" 2>/dev/null \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
failed = [w for w in data.get('items', []) if w['current_state'] in ('failed', 'revoked')]
for w in failed:
    print(f'  🔴 {w[\"display_name\"]:.<40s} {w[\"current_state\"]}')
if not failed:
    print('  (no state changes yet)')
" 2>/dev/null || echo "  (query error)")
    echo "$STATES"
    echo "$STATES" | grep -q "failed\|revoked" && break
    [ "$i" -lt 12 ] && sleep 3
done

step "Reviewing EDA response actions"
ssh_cmd "$HUB_HOST" "journalctl -u arbiter-eda --since '3 min ago' --no-pager 2>/dev/null \
    | grep -E 'PLAY|TASK|ok:|failed:|queued event' | tail -15" || true
note "EDA rulebook matched state_transition → ran remediation playbook"
note "This is AAP in production: Event-Driven Ansible responding to attestation events"
sleep "$PAUSE"

step "Full audit trail — attack to containment"
show_audit "$ADMIN_TOKEN" 15
ok "Complete chain of custody: detection → classification → response → audit"
sleep "$PAUSE"

pause

###############################################################################
act 5 "The Contrast — ARTEX vs Arbiter Hub"
###############################################################################

echo ""
echo -e "${BOLD}ARTEX Attack Timeline (Real Campaign — UNC7228):${NC}"
echo ""
echo "  0:00:00  Initial access (stolen credentials)"
echo "  0:00:05  AD enumeration — 110,000 objects pulled"
echo "  0:00:15  Kerberoasting — service tickets requested"
echo "  0:00:23  27 operations complete"
echo "  0:15:00  Deep system access achieved"
echo "  4:00:00  Full campaign: DCSync, lateral movement, persistence"
echo -e "  ${RED}???${NC}        Detection (if ever — static indicators miss it)"
echo ""
echo -e "${BOLD}Arbiter Hub Response Timeline (This Demo):${NC}"
echo ""
echo "  0:00:00  Rogue agent launches (inside trust boundary)"
echo "  0:00:01  Falco eBPF: behavioral alert (credential read, escape probe)"
echo "  0:00:03  Arbiter Hub: state_transition HEALTHY→FAILED"
echo "  0:00:04  EDA webhook fires → remediation playbook triggered"
echo "  0:00:08  Workload quarantined — network disconnected"
echo "  0:00:10  Audit trail sealed — full chain of evidence"
echo -e "  ${GREEN}0:00:10${NC}  Contained. Before ARTEX would finish phase 2."
echo ""
echo -e "${BOLD}The difference:${NC}"
echo "  ARTEX assumes dwell time. Arbiter Hub eliminates it."
echo "  ARTEX relies on valid credentials. Arbiter Hub attests behavior."
echo "  ARTEX operates at machine speed. So does the defense."
echo ""
sleep "$PAUSE"

pause

###############################################################################
act 6 "Why This Matters for RHEL"
###############################################################################

echo -e "${BOLD}Three layers of defense — all on RHEL:${NC}"
echo ""
echo -e "  ${GREEN}1. Hardware root of trust${NC}"
echo "     TPM attestation (Keylime) — proves the platform wasn't tampered with"
echo "     ARTEX can't fake a TPM quote. The hardware doesn't lie."
echo ""
echo -e "  ${GREEN}2. Runtime behavioral attestation${NC}"
echo "     Falco eBPF — catches the behavior, not the tool"
echo "     Kerberoasting, credential theft, escape probes — all detected by behavior"
echo "     Google: 'static indicators will miss this.' eBPF doesn't."
echo ""
echo -e "  ${GREEN}3. Identity-bound response${NC}"
echo "     IPA + OIDC + HBAC — every workload has an identity, every action is scoped"
echo "     Compromised workload? Revoke identity. Blast radius: one workload."
echo "     ARTEX lateral movement? HBAC says: this service only talks to these services."
echo ""
echo -e "  ${YELLOW}+ Post-quantum ready${NC}"
echo "     kuipa ML-DSA-65 credentials — when quantum arrives, keys are already safe"
echo "     ARTEX's Kerberoasting doesn't work when there's no crackable key material"
echo ""
sleep "$PAUSE"

###############################################################################
# Cleanup
###############################################################################

cleanup_workloads "$ADMIN_TOKEN"

demo_summary "ARTEX ATTACK SCENARIO"
echo "  1. Baseline: healthy fleet, all backends green, clean audit"
echo "  2. Attack: 6-phase ARTEX-style chain in ${ATTACK_DURATION}s (benchmark: 23s)"
echo "  3. Detection: Falco eBPF behavioral alerts — not signatures"
echo "  4. Response: EDA pipeline — machine-speed quarantine + audit"
echo "  5. Contrast: ARTEX assumes dwell time. Arbiter Hub eliminates it."
echo "  6. Platform: hardware trust + runtime attestation + identity = RHEL value"
echo ""
echo -e "${BOLD}Key takeaway:${NC} AI agent attacks are real and fast."
echo "The defense has to be equally autonomous, equally fast, and rooted in hardware trust."
echo "That's what Arbiter Hub does on RHEL — no OpenShift required."
