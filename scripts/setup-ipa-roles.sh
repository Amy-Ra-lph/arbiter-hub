#!/bin/bash
# scripts/setup-ipa-roles.sh
# Sets up IPA roles, groups, and HBAC rules for Arbiter Hub
# Usage: ./setup-ipa-roles.sh EXAMPLE.COM
set -euo pipefail

REALM="${1:?Usage: setup-ipa-roles.sh REALM}"

echo "Setting up Arbiter Hub IPA roles for realm $REALM"

# Groups
for group in attestation-admin attestation-operator attestation-pipeline attestation-viewer attestation-agent; do
    ipa group-add "$group" --desc="Arbiter Hub: $group" 2>/dev/null || echo "Group $group exists"
done

# Roles
ipa role-add "Attestation Admin" --desc="Full arbiter-hub access" 2>/dev/null || true
ipa role-add "Attestation Operator" --desc="Enroll, attest, remediate" 2>/dev/null || true
ipa role-add "Attestation Pipeline" --desc="Attest, sign, verify" 2>/dev/null || true
ipa role-add "Attestation Viewer" --desc="Read-only access" 2>/dev/null || true
ipa role-add "Attestation Agent" --desc="Read + request re-attestation" 2>/dev/null || true

# Associate groups with roles
ipa role-add-member "Attestation Admin" --groups=attestation-admin 2>/dev/null || true
ipa role-add-member "Attestation Operator" --groups=attestation-operator 2>/dev/null || true
ipa role-add-member "Attestation Pipeline" --groups=attestation-pipeline 2>/dev/null || true
ipa role-add-member "Attestation Viewer" --groups=attestation-viewer 2>/dev/null || true
ipa role-add-member "Attestation Agent" --groups=attestation-agent 2>/dev/null || true

# HBAC services
for svc in arbiter-api arbiter-kbs arbiter-mcp arbiter-attest arbiter-sign arbiter-enroll; do
    ipa hbacsvc-add "$svc" --desc="Arbiter Hub: $svc" 2>/dev/null || echo "HBAC service $svc exists"
done

echo "Arbiter Hub IPA setup complete"
touch /etc/arbiter/.ipa-roles-configured
