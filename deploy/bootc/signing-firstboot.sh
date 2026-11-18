#!/usr/bin/env bash
# Arbiter signing node firstboot — runs once after bootc image deploys
# Enrolls IPA client, generates Keylime CAs, cosign keypair, starts registry,
# exports client certs for attestation node
set -euo pipefail

STAMP="/var/lib/arbiter-hub/.signing-firstboot-complete"
CONFIG="/etc/arbiter-hub/config.env"
LOG="/var/log/arbiter-signing-firstboot.log"

[ -f "$STAMP" ] && { echo "Already provisioned, skipping"; exit 0; }

exec > >(tee -a "$LOG") 2>&1
echo "=== Arbiter Signing firstboot: $(date -Iseconds) ==="

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found — inject via cloud-init userdata"
    exit 1
fi
source "$CONFIG"

: "${IPA_DOMAIN:?Set IPA_DOMAIN in config.env}"
: "${IPA_ADMIN_PASSWORD:?Set IPA_ADMIN_PASSWORD in config.env}"
HOSTNAME="${SIGNING_HOSTNAME:-$(hostname -f)}"
IDM_HOST="${IDM_HOSTNAME:?Set IDM_HOSTNAME in config.env}"
HUB_HOST="${HUB_HOSTNAME:?Set HUB_HOSTNAME in config.env}"
COSIGN_PASSWORD="${COSIGN_PASSWORD:-}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"

# Step 1: IPA client enrollment
echo "Enrolling IPA client..."
ipa-client-install \
    --domain="$IPA_DOMAIN" \
    --server="$IDM_HOST" \
    --hostname="$HOSTNAME" \
    --principal=admin \
    --password="$IPA_ADMIN_PASSWORD" \
    --mkhomedir \
    --no-ntp \
    --unattended || echo "IPA client may already be enrolled"

# Step 2: Keylime verifier + registrar CAs
# Generated automatically on first start — /var/lib/keylime/cv_ca/ and /var/lib/keylime/reg_ca/
echo "Starting Keylime verifier and registrar..."

# Set require_ek_cert=false for swtpm environments
VERIFIER_CONF="/etc/keylime/verifier.conf"
REGISTRAR_CONF="/etc/keylime/registrar.conf"
TENANT_CONF="/etc/keylime/tenant.conf"

if [ -f "$VERIFIER_CONF" ]; then
    sed -i 's|^require_ek_cert.*|require_ek_cert = false|' "$VERIFIER_CONF"
fi

systemctl enable --now keylime_verifier keylime_registrar

# Wait for CAs to be generated
for i in $(seq 1 30); do
    [ -f /var/lib/keylime/cv_ca/cacert.crt ] && break
    sleep 2
done

if [ ! -f /var/lib/keylime/cv_ca/cacert.crt ]; then
    echo "ERROR: Keylime verifier CA not generated after 60s"
    exit 1
fi
echo "Keylime CAs generated"

# Step 3: Generate client certs for attestation node
echo "Generating client certs for attestation node..."
CLIENT_DIR="/var/lib/keylime/cv_ca/clients"
mkdir -p "$CLIENT_DIR"

# Use Keylime's CA to issue a client cert
cd /var/lib/keylime/cv_ca
if command -v keylime_ca &>/dev/null; then
    keylime_ca -c create -n attestation-client 2>/dev/null || true
elif [ -f cacert.crt ] && [ -f ca-key.pem ]; then
    openssl req -new -newkey rsa:2048 -nodes \
        -keyout "$CLIENT_DIR/client.key" \
        -out "$CLIENT_DIR/client.csr" \
        -subj "/CN=attestation-client"
    openssl x509 -req -in "$CLIENT_DIR/client.csr" \
        -CA cacert.crt -CAkey ca-key.pem -CAcreateserial \
        -out "$CLIENT_DIR/client.crt" -days 365
    rm -f "$CLIENT_DIR/client.csr"
fi
chmod 644 "$CLIENT_DIR"/*.crt 2>/dev/null || true
chmod 600 "$CLIENT_DIR"/*.key 2>/dev/null || true

echo "Client certs at $CLIENT_DIR — copy ca.crt + client.crt + client.key to attestation node /etc/arbiter/keylime/"

# Step 4: cosign keypair
echo "Generating cosign keypair..."
mkdir -p /etc/arbiter/cosign
export COSIGN_PASSWORD
cosign generate-key-pair --output-key-prefix /etc/arbiter/cosign/cosign 2>/dev/null || \
    cosign generate-key-pair 2>/dev/null  # fallback for older cosign
if [ -f cosign.key ]; then
    mv cosign.key cosign.pub /etc/arbiter/cosign/ 2>/dev/null || true
fi
chmod 600 /etc/arbiter/cosign/cosign.key 2>/dev/null || true
chmod 644 /etc/arbiter/cosign/cosign.pub 2>/dev/null || true
echo "cosign public key at /etc/arbiter/cosign/cosign.pub — copy to attestation node"

# Step 5: Container registry (Quadlet)
echo "Starting container registry..."
cat > /etc/containers/systemd/arbiter-registry.container <<REGUNIT
[Unit]
Description=Arbiter signing registry
After=network-online.target

[Container]
Image=docker.io/library/registry:2
ContainerName=arbiter-registry
PublishPort=${REGISTRY_PORT}:5000
Volume=/var/lib/registry:/var/lib/registry:Z

[Service]
Restart=always

[Install]
WantedBy=multi-user.target default.target
REGUNIT

systemctl daemon-reload
systemctl enable --now arbiter-registry

# Wait for registry
for i in $(seq 1 15); do
    curl -sf http://localhost:${REGISTRY_PORT}/v2/ >/dev/null 2>&1 && break
    sleep 2
done
echo "Registry running on port ${REGISTRY_PORT}"

# Step 6: Export summary
echo ""
echo "=== Signing node ready ==="
echo "Keylime verifier:  https://${HOSTNAME}:8881"
echo "Keylime registrar: https://${HOSTNAME}:8890"
echo "Container registry: http://${HOSTNAME}:${REGISTRY_PORT}"
echo ""
echo "Copy to attestation node:"
echo "  scp /var/lib/keylime/cv_ca/cacert.crt ${HUB_HOST}:/etc/arbiter/keylime/ca.crt"
echo "  scp ${CLIENT_DIR}/client.crt ${HUB_HOST}:/etc/arbiter/keylime/client.crt"
echo "  scp ${CLIENT_DIR}/client.key ${HUB_HOST}:/etc/arbiter/keylime/client.key"
echo "  scp /etc/arbiter/cosign/cosign.pub ${HUB_HOST}:/etc/arbiter/cosign/cosign.pub"

mkdir -p "$(dirname "$STAMP")"
date -Iseconds > "$STAMP"
echo "=== Signing firstboot complete: $(date -Iseconds) ==="
