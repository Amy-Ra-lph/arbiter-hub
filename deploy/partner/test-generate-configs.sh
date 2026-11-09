#!/bin/bash
# Verify generate-configs.sh splits site.env into per-node config.env files
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PASS=0
FAIL=0

assert() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"; PASS=$((PASS+1))
    else
        echo "  FAIL: $desc"; FAIL=$((FAIL+1))
    fi
}

assert_grep() {
    local desc="$1" pattern="$2" file="$3"
    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo "  PASS: $desc"; PASS=$((PASS+1))
    else
        echo "  FAIL: $desc (pattern '$pattern' not in $file)"; FAIL=$((FAIL+1))
    fi
}

# ── Test 1: Generate configs from filled site.env ──────────────────
echo "=== Test: generate-configs splits site.env into per-node configs ==="

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cp site.env.example "$TMPDIR/site.env"

# Fill required fields with test values
sed -i 's|^SITE_DOMAIN=.*|SITE_DOMAIN=test.local|' "$TMPDIR/site.env"
sed -i 's|^SITE_REALM=.*|SITE_REALM=TEST.LOCAL|' "$TMPDIR/site.env"
sed -i 's|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=TestPass123|' "$TMPDIR/site.env"
sed -i 's|^DS_PASSWORD=.*|DS_PASSWORD=TestDS456|' "$TMPDIR/site.env"
sed -i 's|^IPA_HOSTNAME=.*|IPA_HOSTNAME=ipa.test.local|' "$TMPDIR/site.env"
sed -i 's|^HUB_HOSTNAME=.*|HUB_HOSTNAME=hub.test.local|' "$TMPDIR/site.env"
sed -i 's|^SIGNING_HOSTNAME=.*|SIGNING_HOSTNAME=signing.test.local|' "$TMPDIR/site.env"
sed -i 's|^AGENT_HOSTNAMES=.*|AGENT_HOSTNAMES=agent1.test.local|' "$TMPDIR/site.env"
sed -i 's|^DNS_FORWARDER=.*|DNS_FORWARDER=10.0.0.1|' "$TMPDIR/site.env"
sed -i 's|^RHCS_CA_URL=.*|RHCS_CA_URL=https://ca.test.local:8443|' "$TMPDIR/site.env"

./generate-configs.sh --site-env="$TMPDIR/site.env" --output="$TMPDIR/out"

# Assert: 4 base config files created
assert "ipa-config.env exists" test -f "$TMPDIR/out/ipa-config.env"
assert "hub-config.env exists" test -f "$TMPDIR/out/hub-config.env"
assert "signing-config.env exists" test -f "$TMPDIR/out/signing-config.env"
assert "agent-config.env exists" test -f "$TMPDIR/out/agent-config.env"

# Assert: IPA config has correct domain and realm
assert_grep "IPA config has IDM_DOMAIN" "IDM_DOMAIN=test.local" "$TMPDIR/out/ipa-config.env"
assert_grep "IPA config has IDM_REALM" "IDM_REALM=TEST.LOCAL" "$TMPDIR/out/ipa-config.env"
assert_grep "IPA config has IDM_ADMIN_PASSWORD" "IDM_ADMIN_PASSWORD=TestPass123" "$TMPDIR/out/ipa-config.env"
assert_grep "IPA config has IDM_DS_PASSWORD" "IDM_DS_PASSWORD=TestDS456" "$TMPDIR/out/ipa-config.env"
assert_grep "IPA config has PQC_ALGORITHM" "PQC_ALGORITHM=ML-DSA-65" "$TMPDIR/out/ipa-config.env"

# Assert: Hub config references IPA hostname
assert_grep "Hub config has IDM_HOSTNAME" "IDM_HOSTNAME=ipa.test.local" "$TMPDIR/out/hub-config.env"
assert_grep "Hub config has HUB_HOSTNAME" "HUB_HOSTNAME=hub.test.local" "$TMPDIR/out/hub-config.env"
assert_grep "Hub config has IPA_DOMAIN" "IPA_DOMAIN=test.local" "$TMPDIR/out/hub-config.env"

# Assert: Signing config references both IPA and Hub
assert_grep "Signing config has IDM_HOSTNAME" "IDM_HOSTNAME=ipa.test.local" "$TMPDIR/out/signing-config.env"
assert_grep "Signing config has HUB_HOSTNAME" "HUB_HOSTNAME=hub.test.local" "$TMPDIR/out/signing-config.env"

# Assert: Agent config references IPA, Hub, and Signing
assert_grep "Agent config has IDM_HOSTNAME" "IDM_HOSTNAME=ipa.test.local" "$TMPDIR/out/agent-config.env"
assert_grep "Agent config has HUB_HOSTNAME" "HUB_HOSTNAME=hub.test.local" "$TMPDIR/out/agent-config.env"

# ── Test 2: Missing required field fails with field name ───────────
echo ""
echo "=== Test: missing required field fails with clear error ==="

cp site.env.example "$TMPDIR/site-bad.env"
# Leave SITE_DOMAIN empty
sed -i 's|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=test|' "$TMPDIR/site-bad.env"

if ./generate-configs.sh --site-env="$TMPDIR/site-bad.env" --output="$TMPDIR/out-bad" 2>"$TMPDIR/err.log"; then
    echo "  FAIL: should have failed on missing SITE_DOMAIN"; FAIL=$((FAIL+1))
else
    if grep -q "SITE_DOMAIN" "$TMPDIR/err.log"; then
        echo "  PASS: failed with SITE_DOMAIN in error message"; PASS=$((PASS+1))
    else
        echo "  FAIL: failed but error didn't name SITE_DOMAIN"; FAIL=$((FAIL+1))
    fi
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "=== generate-configs: ${PASS} pass, ${FAIL} fail ==="
test "$FAIL" -eq 0
