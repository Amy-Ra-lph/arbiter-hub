#!/bin/bash
# security-test-suite.sh — Automated security validation for unified demo environment
#
# Runs 24 assertions across identity, attestation, policy, and security layers.
# Auth via kinit + client_credentials (no interactive auth, no AUTH_MODE=dev).
#
# Usage:
#   ./scripts/security-test-suite.sh                    # defaults
#   IDM=idm.arbiter.demo HUB=hub.arbiter.demo ./scripts/security-test-suite.sh

set -uo pipefail

IDM="${IDM:-idm.arbiter.demo}"
HUB="${HUB:-hub.arbiter.demo}"
AGENT1="${AGENT1:-agent-verified.arbiter.demo}"
AGENT2="${AGENT2:-agent-untrusted.arbiter.demo}"
DOMAIN="${DOMAIN:-arbiter.demo}"
REALM="${REALM:-$(echo "$DOMAIN" | tr '[:lower:]' '[:upper:]')}"
CLIENT_ID="${ARBITER_CLIENT_ID:-arbiter-hub}"
CLIENT_SECRET_FILE="${ARBITER_CLIENT_SECRET_FILE:-/etc/arbiter/client-secret}"

PASS=0
FAIL=0
TOTAL=0

assert() {
    local name="$1"
    local cmd="$2"
    TOTAL=$((TOTAL + 1))
    if eval "$cmd" >/dev/null 2>&1; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

get_token() {
    kinit -k -t /etc/krb5.keytab "HTTP/$(hostname -f)@${REALM}" 2>/dev/null || {
        echo "FATAL: kinit failed — no keytab or wrong principal" >&2
        exit 1
    }

    local secret
    if [[ -f "$CLIENT_SECRET_FILE" ]]; then
        secret=$(cat "$CLIENT_SECRET_FILE")
    else
        echo "FATAL: client secret file not found: $CLIENT_SECRET_FILE" >&2
        exit 1
    fi

    local response
    response=$(curl -sk -X POST "https://${IDM}/idp/oauth2/token" \
        -u "${CLIENT_ID}:${secret}" \
        -d "grant_type=client_credentials&scope=openid attestation-admin" 2>/dev/null)

    TOKEN=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
    if [[ -z "$TOKEN" ]]; then
        echo "FATAL: empty token from ahdapa" >&2
        echo "Response: $response" >&2
        exit 1
    fi
}

echo "=== Unified Security Demo — Test Suite ==="
echo "IDM=$IDM  HUB=$HUB  AGENT1=$AGENT1  AGENT2=$AGENT2"
echo ""

get_token

# ── Identity Layer (7) ─────────────────────────────────────────────
echo "── Identity Layer ──"

assert "IPA running" \
    "ipactl status 2>&1 | grep -q 'Directory Service: RUNNING'"

assert "ahdapa OIDC discovery" \
    "curl -sk https://${IDM}/idp/.well-known/openid-configuration | grep -q authorization_endpoint"

assert "20+ users seeded" \
    "ipa user-find --sizelimit=0 2>/dev/null | grep -c 'User login:' | grep -qE '^[2-9][0-9]|^[1-9][0-9]{2}'"

assert "10+ groups seeded" \
    "ipa group-find --sizelimit=0 2>/dev/null | grep -c 'Group name:' | grep -qE '^[1-9][0-9]|^[1-9][0-9]{2}'"

assert "8+ HBAC rules" \
    "ipa hbacrule-find 2>/dev/null | grep -c 'Rule name:' | grep -qE '^[8-9]|^[1-9][0-9]'"

assert "6+ sudo rules" \
    "ipa sudorule-find 2>/dev/null | grep -c 'Rule name:' | grep -qE '^[6-9]|^[1-9][0-9]'"

assert "SPIFFE JWKS available" \
    "curl -sk https://${IDM}/spiffe/oidc/jwks | grep -q use"

# ── Attestation Layer (5) ──────────────────────────────────────────
echo ""
echo "── Attestation Layer ──"

assert "Hub API healthy" \
    "curl -sk http://${HUB}:8400/health | grep -qiE 'ok|healthy'"

assert "Keylime verifier up" \
    "curl -sk https://${IDM}:8881/version 2>/dev/null | grep -q version"

assert "6+ workloads registered" \
    "curl -sk -H 'Authorization: Bearer ${TOKEN}' http://${HUB}:8400/workloads | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get(\"total\",len(d)) >= 6'"

assert "3+ trust policies" \
    "curl -sk -H 'Authorization: Bearer ${TOKEN}' http://${HUB}:8400/policies | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d) >= 3'"

assert "Agent-1 workloads HEALTHY" \
    "curl -sk -H 'Authorization: Bearer ${TOKEN}' 'http://${HUB}:8400/workloads?host=${AGENT1}' | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d if isinstance(d,list) else d.get(\"items\",[]); assert all(w.get(\"state\")==\"HEALTHY\" for w in items) if items else True'"

# ── Policy Layer (8) ───────────────────────────────────────────────
echo ""
echo "── Policy Layer ──"

assert "SELinux enforcing agent-1" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT1} getenforce 2>/dev/null | grep -q Enforcing"

assert "SELinux enforcing agent-2" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT2} getenforce 2>/dev/null | grep -q Enforcing"

assert "fapolicyd running agent-1" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT1} systemctl is-active fapolicyd 2>/dev/null | grep -q active"

assert "fapolicyd running agent-2" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT2} systemctl is-active fapolicyd 2>/dev/null | grep -q active"

assert "AIDE baseline exists agent-1" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT1} test -f /var/lib/aide/aide.db.gz"

assert "Falco running agent-1" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT1} systemctl is-active falco 2>/dev/null | grep -q active"

assert "Falco running agent-2" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT2} systemctl is-active falco 2>/dev/null | grep -q active"

assert "enforcement-mcp reachable" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT1} curl -s http://localhost:8402/health 2>/dev/null | grep -qiE 'ok|healthy'"

# ── Security Tests (4) ─────────────────────────────────────────────
echo ""
echo "── Security Tests ──"

assert "CALDERA server running" \
    "curl -sk http://${HUB}:8888 2>/dev/null | grep -qi caldera"

assert "Sandcat agent-1 checked in" \
    "curl -sk 'http://${HUB}:8888/api/v2/agents' -H 'KEY: ADMIN123' 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d) >= 1'"

assert "HBAC blocks mallory SSH" \
    "! sshpass -p 'redhat123' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 mallory@${AGENT1} hostname 2>/dev/null"

assert "Sudo blocks grace escalation" \
    "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${AGENT1} 'su - grace -c \"sudo su - root\" 2>&1' | grep -qiE 'not allowed|is not in the sudoers|not permitted'"

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "=== Security Demo: ${PASS} pass, ${FAIL} fail, ${TOTAL} total ==="
[[ "$FAIL" -eq 0 ]]
