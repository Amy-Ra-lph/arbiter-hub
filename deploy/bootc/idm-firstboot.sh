#!/usr/bin/env bash
# Arbiter Hub IdM node firstboot — runs once after bootc image deploys
# Installs IPA server, configures swtpm, starts Keylime verifier
# Config: /etc/arbiter-hub/config.env
set -euo pipefail

STAMP="/var/lib/arbiter-hub/.idm-firstboot-complete"
CONFIG="/etc/arbiter-hub/config.env"
LOG="/var/log/arbiter-idm-firstboot.log"

[ -f "$STAMP" ] && { echo "Already provisioned, skipping"; exit 0; }

exec > >(tee -a "$LOG") 2>&1
echo "=== Arbiter Hub IdM firstboot: $(date -Iseconds) ==="

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found — inject via cloud-init userdata"
    exit 1
fi
source "$CONFIG"

# Required vars
: "${IPA_REALM:?Set IPA_REALM in config.env}"
: "${IPA_DOMAIN:?Set IPA_DOMAIN in config.env}"
: "${IPA_ADMIN_PASSWORD:?Set IPA_ADMIN_PASSWORD in config.env}"
: "${IPA_DS_PASSWORD:?Set IPA_DS_PASSWORD in config.env}"
HOSTNAME="${IDM_HOSTNAME:-$(hostname -f)}"

echo "Installing FreeIPA server: realm=${IPA_REALM} domain=${IPA_DOMAIN}"
ipa-server-install \
    --realm="$IPA_REALM" \
    --domain="$IPA_DOMAIN" \
    --hostname="$HOSTNAME" \
    --admin-password="$IPA_ADMIN_PASSWORD" \
    --ds-password="$IPA_DS_PASSWORD" \
    --setup-dns \
    --auto-forwarders \
    --no-host-dns \
    --unattended

echo "FreeIPA server installed"

# swtpm for demo/lab (production would use hardware TPM)
echo "Configuring swtpm..."
mkdir -p /var/lib/swtpm-localca
swtpm_setup --tpmstate /var/lib/swtpm-localca --tpm2 --createek --create-ek-cert --create-platform-cert
systemctl start swtpm-setup-arbiter || true

# Keylime verifier + registrar
echo "Starting Keylime verifier and registrar..."
systemctl start keylime_verifier keylime_registrar
systemctl is-active keylime_verifier keylime_registrar

# ahdapa OIDC provider (if configured)
if [ -n "${AHDAPA_INSTALL:-}" ]; then
    echo "Installing ahdapa OIDC provider..."
    pip install ahdapa
    # ahdapa post-install hooks go here
fi

mkdir -p "$(dirname "$STAMP")"
date -Iseconds > "$STAMP"
echo "=== IdM firstboot complete: $(date -Iseconds) ==="
