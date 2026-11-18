#!/bin/bash
# Verify deploy.sh --target=kvm --dry-run generates correct virt-install commands
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

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Create filled site.env
cp site.env.example "$TMPDIR/site.env"
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

echo "=== Test: deploy.sh --target=kvm --dry-run ==="

OUTPUT=$(./deploy.sh --site-env="$TMPDIR/site.env" --target=kvm --dry-run --work-dir="$TMPDIR" 2>&1)

# Assert: generates virt-install commands for each node role in order
assert "virt-install for ipa" echo "$OUTPUT" \| grep -q "virt-install.*ipa"
assert "virt-install for hub" echo "$OUTPUT" \| grep -q "virt-install.*hub"
assert "virt-install for signing" echo "$OUTPUT" \| grep -q "virt-install.*signing"
assert "virt-install for agent" echo "$OUTPUT" \| grep -q "virt-install.*agent"

# Assert: cloud-init user-data files created
assert "ipa user-data exists" test -f "$TMPDIR/cloud-init/ipa-user-data.yaml"
assert "hub user-data exists" test -f "$TMPDIR/cloud-init/hub-user-data.yaml"
assert "signing user-data exists" test -f "$TMPDIR/cloud-init/signing-user-data.yaml"
assert "agent user-data exists" test -f "$TMPDIR/cloud-init/agent1-user-data.yaml"

# Assert: user-data contains config.env content
assert "ipa user-data has domain" grep -q "test.local" "$TMPDIR/cloud-init/ipa-user-data.yaml"
assert "hub user-data has IPA ref" grep -q "ipa.test.local" "$TMPDIR/cloud-init/hub-user-data.yaml"

# Assert: IPA deployed before Hub (line number ordering)
IPA_LINE=$(echo "$OUTPUT" | grep -n "virt-install.*ipa" | head -1 | cut -d: -f1)
HUB_LINE=$(echo "$OUTPUT" | grep -n "virt-install.*hub" | head -1 | cut -d: -f1)
assert "IPA before Hub in output" test "$IPA_LINE" -lt "$HUB_LINE"

# Assert: signing before agent
SIGN_LINE=$(echo "$OUTPUT" | grep -n "virt-install.*signing" | head -1 | cut -d: -f1)
AGENT_LINE=$(echo "$OUTPUT" | grep -n "virt-install.*agent" | head -1 | cut -d: -f1)
assert "Signing before Agent in output" test "$SIGN_LINE" -lt "$AGENT_LINE"

# Assert: generated node configs exist
assert "ipa-config.env generated" test -f "$TMPDIR/configs/ipa-config.env"
assert "hub-config.env generated" test -f "$TMPDIR/configs/hub-config.env"

echo ""
echo "=== deploy dry-run: ${PASS} pass, ${FAIL} fail ==="
test "$FAIL" -eq 0
