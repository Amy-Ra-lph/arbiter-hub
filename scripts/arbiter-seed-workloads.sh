#!/bin/bash
# arbiter-seed-workloads.sh — Register workloads and trust policies in Arbiter Hub
#
# Registers 6 workloads and 3 trust policies via Hub API.
# Idempotent — 409 (already exists) treated as success.
#
# Usage:
#   ./scripts/arbiter-seed-workloads.sh
#   HUB=hub.arbiter.demo IDM=idm.arbiter.demo ./scripts/arbiter-seed-workloads.sh

set -euo pipefail

HUB="${HUB:-hub.arbiter.demo}"
IDM="${IDM:-idm.arbiter.demo}"
HUB_API="http://${HUB}:8400"
DOMAIN="${DOMAIN:-arbiter.demo}"
REALM="${REALM:-$(echo "$DOMAIN" | tr '[:lower:]' '[:upper:]')}"
CLIENT_ID="${ARBITER_CLIENT_ID:-arbiter-hub}"
CLIENT_SECRET_FILE="${ARBITER_CLIENT_SECRET_FILE:-/etc/arbiter/client-secret}"

PASS=0
FAIL=0
TOTAL=0

log()  { echo "[seed] $*"; }
ok()   { echo "[  ok] $*"; PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); }
fail() { echo "[FAIL] $*" >&2; FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); }

get_token() {
    kinit -k -t /etc/krb5.keytab "HTTP/${HUB}.@${REALM}" 2>/dev/null || \
        kinit -k -t /etc/krb5.keytab "HTTP/$(hostname -f)@${REALM}" 2>/dev/null || \
        { log "FATAL: kinit failed"; exit 1; }

    local secret
    if [[ -f "$CLIENT_SECRET_FILE" ]]; then
        secret=$(cat "$CLIENT_SECRET_FILE")
    else
        log "FATAL: client secret file not found: $CLIENT_SECRET_FILE"
        exit 1
    fi

    local response
    response=$(curl -sk -X POST "https://${IDM}/idp/oauth2/token" \
        -u "${CLIENT_ID}:${secret}" \
        -d "grant_type=client_credentials&scope=openid attestation-admin" 2>/dev/null)

    TOKEN=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
    if [[ -z "$TOKEN" ]]; then
        log "FATAL: empty token from ahdapa. Response: $response"
        exit 1
    fi
    log "Token acquired (${TOKEN:0:12}...)"
}

register_policy() {
    local name="$1" backends="$2" interval="$3" action="$4"
    local status
    status=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "${HUB_API}/policies" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -H "Origin: ${HUB_API}" \
        -d "{
            \"name\": \"${name}\",
            \"backends_required\": ${backends},
            \"attestation_interval_seconds\": ${interval},
            \"failure_action\": \"${action}\"
        }")
    case "$status" in
        200|201) ok "Policy: ${name} (created)" ;;
        409)     ok "Policy: ${name} (exists)" ;;
        *)       fail "Policy: ${name} (HTTP ${status})" ;;
    esac
}

register_workload() {
    local name="$1" agent="$2" tier="$3" wtype="$4" policy="$5"
    local principal="service/${name}@${REALM}"
    local status
    status=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "${HUB_API}/workloads" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -H "Origin: ${HUB_API}" \
        -d "{
            \"name\": \"${name}\",
            \"ipa_principal\": \"${principal}\",
            \"display_name\": \"${name}\",
            \"workload_type\": \"${wtype}\",
            \"trust_tier\": \"${tier}\",
            \"policy\": \"${policy}\",
            \"agent_host\": \"${agent}.${DOMAIN}\",
            \"backend_types\": [\"keylime\"]
        }")
    case "$status" in
        200|201) ok "Workload: ${name} on ${agent} (${tier})" ;;
        409)     ok "Workload: ${name} on ${agent} (exists)" ;;
        *)       fail "Workload: ${name} on ${agent} (HTTP ${status})" ;;
    esac
}

# ── Auth ───────────────────────────────────────────────────────────
log "Seeding Arbiter Hub at ${HUB_API} (domain=${DOMAIN})"
get_token

# ── Trust Policies (3) ────────────────────────────────────────────
log "Registering trust policies..."

register_policy "sovereign-policy" \
    '["keylime"]' \
    3600 \
    "alert-only"

register_policy "verified-policy" \
    '["keylime", "cosign"]' \
    900 \
    "quarantine"

register_policy "untrusted-policy" \
    '["keylime", "cosign", "measured-boot"]' \
    300 \
    "revoke"

# ── Workloads (6) ─────────────────────────────────────────────────
log "Registering workloads..."

register_workload "enforcement-mcp" "agent-verified" "sovereign" "security-tool" "sovereign-policy"
register_workload "data-pipeline"   "agent-verified" "verified"  "batch-job"     "verified-policy"
register_workload "compliance-scanner" "agent-verified" "verified" "scanner"     "verified-policy"
register_workload "vibe-coded-tool" "agent-untrusted" "untrusted" "mcp-tool"    "untrusted-policy"
register_workload "model-serve"     "agent-untrusted" "untrusted" "inference"   "untrusted-policy"
register_workload "rogue-agent"     "agent-untrusted" "untrusted" "adversary"   "untrusted-policy"

# ── Summary ───────────────────────────────────────────────────────
echo ""
log "=== Arbiter Seed: ${PASS} ok, ${FAIL} fail, ${TOTAL} total ==="
[[ "$FAIL" -eq 0 ]]
