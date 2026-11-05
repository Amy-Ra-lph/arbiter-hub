#!/usr/bin/env bash
# Arbiter Hub node firstboot — runs once after bootc image deploys
# Enrolls IPA client, requests TLS cert, configures nginx, starts containers + EDA
set -euo pipefail

STAMP="/var/lib/arbiter-hub/.hub-firstboot-complete"
CONFIG="/etc/arbiter-hub/config.env"
LOG="/var/log/arbiter-hub-firstboot.log"

[ -f "$STAMP" ] && { echo "Already provisioned, skipping"; exit 0; }

exec > >(tee -a "$LOG") 2>&1
echo "=== Arbiter Hub firstboot: $(date -Iseconds) ==="

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found — inject via cloud-init userdata"
    exit 1
fi
source "$CONFIG"

: "${IPA_DOMAIN:?Set IPA_DOMAIN in config.env}"
: "${IPA_ADMIN_PASSWORD:?Set IPA_ADMIN_PASSWORD in config.env}"
: "${DB_PASSWORD:?Set DB_PASSWORD in config.env}"
HOSTNAME="${HUB_HOSTNAME:-$(hostname -f)}"
IDM_HOST="${IDM_HOSTNAME:?Set IDM_HOSTNAME in config.env}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"
ARBITER_SERVICE_PASSWORD="${ARBITER_SERVICE_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"
API_PORT="${API_PORT:-8400}"
MCP_PORT="${MCP_PORT:-8401}"
UI_PORT="${UI_PORT:-8402}"
EDA_PORT="${EDA_PORT:-5001}"

# Step 1: IPA client enrollment
echo "Enrolling IPA client..."
echo "$IPA_ADMIN_PASSWORD" | ipa-client-install \
    --domain="$IPA_DOMAIN" \
    --server="$IDM_HOST" \
    --hostname="$HOSTNAME" \
    --principal=admin \
    --password="$IPA_ADMIN_PASSWORD" \
    --mkhomedir \
    --no-ntp \
    --unattended || echo "IPA client may already be enrolled"

# Step 2: TLS cert from IPA via certmonger
echo "Requesting TLS certificate..."
mkdir -p /etc/pki/arbiter-hub
ipa-getcert request \
    -w -k /etc/pki/arbiter-hub/server.key \
    -f /etc/pki/arbiter-hub/server.crt \
    -D "$HOSTNAME" \
    -K "HTTP/$HOSTNAME" \
    -N "CN=$HOSTNAME" \
    -C "systemctl reload nginx" || echo "certmonger request may already exist"

# Step 3: SPNEGO keytab for API container (Kerberos service auth)
# Allows agents to authenticate with host keytab instead of shared password
echo "Configuring Kerberos service authentication..."
SPNEGO_KEYTAB="/etc/arbiter-hub/http.keytab"
if command -v ipa &>/dev/null && klist -s 2>/dev/null; then
    echo "$IPA_ADMIN_PASSWORD" | kinit admin 2>/dev/null || true
    ipa service-add "HTTP/$HOSTNAME" 2>/dev/null || echo "HTTP service principal may already exist"
    ipa-getkeytab -s "$IDM_HOST" -p "HTTP/$HOSTNAME" -k "$SPNEGO_KEYTAB" 2>/dev/null || true
    chmod 640 "$SPNEGO_KEYTAB"
    SPNEGO_AVAILABLE=true
else
    echo "IPA CLI not available — SPNEGO disabled, password auth only"
    SPNEGO_AVAILABLE=false
fi

# Step 4: nginx config from template
echo "Configuring nginx TLS termination..."
if [ -f /etc/nginx/conf.d/arbiter-hub.conf.template ]; then
    sed -e "s|__HOSTNAME__|$HOSTNAME|g" \
        -e "s|__API_PORT__|$API_PORT|g" \
        -e "s|__MCP_PORT__|$MCP_PORT|g" \
        -e "s|__UI_PORT__|$UI_PORT|g" \
        -e "s|__EDA_PORT__|$EDA_PORT|g" \
        /etc/nginx/conf.d/arbiter-hub.conf.template \
        > /etc/nginx/conf.d/arbiter-hub.conf
fi
setsebool -P httpd_can_network_connect on 2>/dev/null || true
systemctl enable --now nginx

# Step 5: Container env drop-ins
echo "Configuring container environment..."
mkdir -p /etc/containers/systemd/arbiter-hub-api.container.d \
         /etc/containers/systemd/arbiter-hub-db.container.d

# DB password
cat > /etc/containers/systemd/arbiter-hub-db.container.d/password.conf <<DROPIN
[Container]
Environment=POSTGRESQL_PASSWORD=${DB_PASSWORD}
DROPIN

# Service auth: SPNEGO (primary) + password (fallback)
SPNEGO_MOUNT=""
SPNEGO_ENV=""
if [ "$SPNEGO_AVAILABLE" = true ] && [ -f "$SPNEGO_KEYTAB" ]; then
    SPNEGO_MOUNT="Volume=${SPNEGO_KEYTAB}:/etc/arbiter-hub/http.keytab:ro,Z"
    SPNEGO_ENV="Environment=ARBITER_SPNEGO_ENABLED=true
Environment=ARBITER_SPNEGO_KEYTAB=/etc/arbiter-hub/http.keytab
Environment=ARBITER_SPNEGO_PRINCIPAL=HTTP/$HOSTNAME"
fi

cat > /etc/containers/systemd/arbiter-hub-api.container.d/service-auth.conf <<DROPIN
[Container]
Environment=ARBITER_LOCAL_ADMIN_ENABLED=true
Environment=ARBITER_LOCAL_ADMIN_PASSWORD=${ARBITER_SERVICE_PASSWORD}
${SPNEGO_ENV}
${SPNEGO_MOUNT}
DROPIN

# Step 6: Start quadlet containers
echo "Starting containers..."
systemctl daemon-reload
systemctl start arbiter-hub-db arbiter-hub-api arbiter-hub-mcp arbiter-hub-ui

# Wait for API
for i in $(seq 1 30); do
    curl -sf http://localhost:${API_PORT}/health >/dev/null 2>&1 && break
    sleep 2
done

# Step 7: EDA controller
echo "Configuring EDA controller..."
mkdir -p /etc/arbiter
echo "$WEBHOOK_SECRET" > /etc/arbiter/webhook-secret
chmod 600 /etc/arbiter/webhook-secret

# EDA inventory with resolved values
cat > /opt/arbiter-eda/inventory/hosts.yml <<EDAINV
---
all:
  vars:
    arbiter_api_url: http://localhost:${API_PORT}
    arbiter_webhook_secret: ${WEBHOOK_SECRET}
    arbiter_service_password: ${ARBITER_SERVICE_PASSWORD}
  children:
    server:
      hosts:
        ${HOSTNAME}:
          ansible_connection: local
    client:
      hosts:
        ${AGENT_HOSTNAME:-agent}:
          ansible_host: ${AGENT_IP:-127.0.0.1}
EDAINV
chmod 600 /opt/arbiter-eda/inventory/hosts.yml

# EDA systemd unit
cat > /etc/systemd/system/arbiter-eda.service <<EDASVC
[Unit]
Description=Arbiter Hub EDA Controller (ansible-rulebook)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ansible-rulebook \
  --rulebook /opt/arbiter-eda/rulebooks/attestation.yml \
  --inventory /opt/arbiter-eda/inventory/hosts.yml \
  --source-dir /opt/arbiter-eda/plugins/event_source
WorkingDirectory=/opt/arbiter-eda
Environment=ARBITER_WEBHOOK_SECRET=${WEBHOOK_SECRET}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EDASVC

systemctl daemon-reload
systemctl enable --now arbiter-eda

# Step 8: Register webhook
echo "Registering EDA webhook..."
for i in $(seq 1 10); do
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:${API_PORT}/api/webhooks \
        -H "Content-Type: application/json" \
        -H "Origin: http://localhost:${API_PORT}" \
        -d "{\"url\":\"http://localhost:${EDA_PORT}/\",\"events\":[\"state_transition\"],\"secret\":\"${WEBHOOK_SECRET}\",\"active\":true}" 2>/dev/null)
    [ "$HTTP" = "200" ] || [ "$HTTP" = "201" ] || [ "$HTTP" = "409" ] && break
    sleep 3
done
echo "Webhook registration: HTTP $HTTP"

echo "Auth modes: SPNEGO=$SPNEGO_AVAILABLE password=true"
mkdir -p "$(dirname "$STAMP")"
date -Iseconds > "$STAMP"
echo "=== Hub firstboot complete: $(date -Iseconds) ==="
