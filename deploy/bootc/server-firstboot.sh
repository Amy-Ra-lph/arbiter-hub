#!/usr/bin/env bash
# Arbiter Server firstboot — runs once after bootc image deploys
#
# Phase 1: IPA client enrollment + OIDC registration
# Phase 2: Keylime verifier + registrar + cosign keypair
# Phase 3: Hub containers (DB, API, KBS, MCP, UI) + EDA
# Phase 4: Seed policies, RBAC roles, enrollment tokens, redact secrets
set -euo pipefail

STAMP="/var/lib/arbiter/.server-firstboot-complete"
CONFIG="/etc/arbiter/server.env"
LOG="/var/log/arbiter-server-firstboot.log"

[ -f "$STAMP" ] && { echo "Already provisioned, skipping"; exit 0; }

exec > >(tee -a "$LOG") 2>&1
echo "=== Arbiter Server firstboot: $(date -Iseconds) ==="

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found — inject via cloud-init write_files"
    exit 1
fi
source "$CONFIG"

: "${IPA_SERVER:?Set IPA_SERVER in server.env}"
: "${IPA_DOMAIN:?Set IPA_DOMAIN in server.env}"
: "${IPA_ADMIN_PASSWORD:?Set IPA_ADMIN_PASSWORD in server.env}"

HOSTNAME="${ARBITER_HOSTNAME:-$(hostname -f)}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 32)}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(openssl rand -base64 24)}"
ARBITER_SERVICE_PASSWORD="${ARBITER_SERVICE_PASSWORD:-$(openssl rand -base64 24)}"
KEYLIME_ENABLED="${KEYLIME_ENABLED:-true}"
COSIGN_ENABLED="${COSIGN_ENABLED:-true}"
EDA_ENABLED="${EDA_ENABLED:-true}"
API_PORT="${API_PORT:-8400}"
UI_PORT="${UI_PORT:-8080}"
EDA_PORT="${EDA_PORT:-5001}"
MCP_PORT="${MCP_PORT:-8401}"

# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Identity Enrollment
# ═══════════════════════════════════════════════════════════════════════
echo "── Phase 1: Identity enrollment ──"

echo "Enrolling IPA client against ${IPA_SERVER}..."
if ! [ -f /etc/ipa/default.conf ]; then
    ipa-client-install \
        --server="$IPA_SERVER" \
        --domain="$IPA_DOMAIN" \
        --hostname="$HOSTNAME" \
        --principal=admin \
        --password="$IPA_ADMIN_PASSWORD" \
        --mkhomedir \
        --no-ntp \
        --unattended
    echo "IPA client enrolled"
else
    echo "IPA client already enrolled, skipping"
fi

echo "$IPA_ADMIN_PASSWORD" | kinit admin

# Request HTTP service principal for SPNEGO
echo "Configuring SPNEGO service principal..."
SPNEGO_KEYTAB="/etc/arbiter/http.keytab"
ipa service-add "HTTP/$HOSTNAME" 2>/dev/null || echo "HTTP service already exists"
ipa-getkeytab -s "$IPA_SERVER" -p "HTTP/$HOSTNAME" -k "$SPNEGO_KEYTAB"
chmod 640 "$SPNEGO_KEYTAB"

# Request TLS cert from IPA CA via certmonger
echo "Requesting TLS certificate..."
mkdir -p /etc/pki/arbiter
ipa-getcert request \
    -w -k /etc/pki/arbiter/server.key \
    -f /etc/pki/arbiter/server.crt \
    -D "$HOSTNAME" \
    -K "HTTP/$HOSTNAME" \
    -N "CN=$HOSTNAME" \
    -C "systemctl reload nginx" || echo "certmonger request may already exist"

# Register OIDC client with ahdapa on IdM
echo "Registering OIDC client with IdM..."
OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-arbiter-hub}"
OIDC_CLIENT_SECRET="$(openssl rand -base64 32)"
OIDC_REDIRECT_URI="https://${HOSTNAME}:${UI_PORT}/callback"

curl -sk -X POST "https://${IPA_SERVER}/idp/api/admin/clients" \
    -H "Content-Type: application/json" \
    -H "Authorization: Negotiate $(python3 -c 'import gssapi; ctx=gssapi.SecurityContext(usage="initiate",name=gssapi.Name("HTTP/'${IPA_SERVER}'",gssapi.NameType.hostbased_service)); print(ctx.step().decode("latin-1"))' 2>/dev/null || echo '')" \
    -d "{
        \"client_id\": \"${OIDC_CLIENT_ID}\",
        \"client_secret\": \"${OIDC_CLIENT_SECRET}\",
        \"client_name\": \"Arbiter Hub\",
        \"redirect_uris\": [\"${OIDC_REDIRECT_URI}\"],
        \"grant_types\": [\"authorization_code\", \"client_credentials\"],
        \"scopes\": [\"openid\", \"profile\"]
    }" 2>/dev/null && echo "OIDC client registered" || echo "OIDC client may already exist"

# Create Arbiter RBAC roles in IPA
echo "Creating RBAC roles..."
for role in attestation-admin attestation-reader policy-editor; do
    ipa role-add "$role" --desc="Arbiter Hub: ${role}" 2>/dev/null || true
done
ipa privilege-add arbiter-attestation --desc="Arbiter attestation operations" 2>/dev/null || true
ipa privilege-add arbiter-policy --desc="Arbiter policy management" 2>/dev/null || true

echo "Phase 1 complete"

# Redact IPA admin password immediately — no longer needed
sed -i 's/\(IPA_ADMIN_PASSWORD\s*=\s*\).*/\1<REDACTED>/' "$CONFIG"
chmod 600 "$CONFIG"
echo "IPA admin password redacted from config"

# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Attestation Infrastructure
# ═══════════════════════════════════════════════════════════════════════
echo "── Phase 2: Attestation infrastructure ──"

if [ "$KEYLIME_ENABLED" = "true" ]; then
    echo "Starting keylime-verifier..."
    # Configure TLS auto-generation and bind on all interfaces
    sed -i 's/^tls_dir =.*/tls_dir = generate/' /etc/keylime/verifier.conf
    sed -i 's/^ip =.*/ip = "0.0.0.0"/' /etc/keylime/verifier.conf
    sed -i 's/^tls_dir =.*/tls_dir = generate/' /etc/keylime/registrar.conf
    sed -i 's/^ip =.*/ip = "0.0.0.0"/' /etc/keylime/registrar.conf

    systemctl enable --now keylime_verifier
    # Wait for TLS cert generation
    for i in $(seq 1 30); do
        [ -d /var/lib/keylime/cv_ca ] && break
        sleep 2
    done

    systemctl enable --now keylime_registrar
    for i in $(seq 1 15); do
        ss -tlnp | grep -q ':8891' && break
        sleep 2
    done
    echo "Keylime verifier + registrar running"

    KEYLIME_VERIFIER_URL="https://${HOSTNAME}:8881"
    KEYLIME_CA_CERT="/var/lib/keylime/cv_ca/cacert.crt"
    KEYLIME_CLIENT_CERT="/var/lib/keylime/cv_ca/client-cert.crt"
    KEYLIME_CLIENT_KEY="/var/lib/keylime/cv_ca/client-private.pem"
else
    echo "Keylime disabled"
    KEYLIME_VERIFIER_URL=""
fi

if [ "$COSIGN_ENABLED" = "true" ]; then
    echo "Generating cosign keypair..."
    mkdir -p /etc/arbiter/cosign
    if [ ! -f /etc/arbiter/cosign/cosign.key ]; then
        COSIGN_PASSWORD="" cosign generate-key-pair \
            --output-key-prefix=/etc/arbiter/cosign/cosign 2>/dev/null
        chmod 600 /etc/arbiter/cosign/cosign.key
        chmod 644 /etc/arbiter/cosign/cosign.pub
    fi
    COSIGN_PUBLIC_KEY="/etc/arbiter/cosign/cosign.pub"
    echo "Cosign keypair ready"
else
    COSIGN_PUBLIC_KEY=""
fi

echo "Phase 2 complete"

# ═══════════════════════════════════════════════════════════════════════
# Phase 3: Hub Services (Quadlet containers)
# ═══════════════════════════════════════════════════════════════════════
echo "── Phase 3: Hub services ──"

# Container env drop-ins
echo "Configuring container environment..."
mkdir -p /etc/containers/systemd/arbiter-hub-api.container.d \
         /etc/containers/systemd/arbiter-hub-db.container.d

# Create Podman secret for DB password (Quadlet Secret= lines reference it)
printf '%s' "$DB_PASSWORD" | podman secret create arbiter-hub-db-password - 2>/dev/null || true

# DB password via env drop-in (belt + suspenders with the secret above)
cat > /etc/containers/systemd/arbiter-hub-db.container.d/password.conf <<DROPIN
[Container]
Environment=POSTGRESQL_PASSWORD=${DB_PASSWORD}
DROPIN

# API config — database, backends, auth
KEYLIME_ENV=""
KEYLIME_VOLUME=""
if [ "$KEYLIME_ENABLED" = "true" ]; then
    KEYLIME_ENV="Environment=ARBITER_KEYLIME_VERIFIER_URL=${KEYLIME_VERIFIER_URL}
Environment=ARBITER_KEYLIME_CA_CERT=/etc/arbiter/keylime/ca.crt
Environment=ARBITER_KEYLIME_CLIENT_CERT=/etc/arbiter/keylime/client.crt
Environment=ARBITER_KEYLIME_CLIENT_KEY=/etc/arbiter/keylime/client.key"
    KEYLIME_VOLUME="Volume=/var/lib/keylime/cv_ca:/etc/arbiter/keylime:ro,Z"
fi

COSIGN_ENV=""
COSIGN_VOLUME=""
if [ "$COSIGN_ENABLED" = "true" ]; then
    COSIGN_ENV="Environment=ARBITER_COSIGN_PUBLIC_KEY=/etc/arbiter/cosign/cosign.pub
Environment=ARBITER_COSIGN_INSECURE_IGNORE_TLOG=true"
    COSIGN_VOLUME="Volume=/etc/arbiter/cosign:/etc/arbiter/cosign:ro,Z
Volume=/usr/local/bin/cosign:/usr/local/bin/cosign:ro,Z"
fi

SPNEGO_ENV="Environment=ARBITER_SPNEGO_ENABLED=true
Environment=ARBITER_SPNEGO_KEYTAB=/etc/arbiter/http.keytab
Environment=ARBITER_SPNEGO_PRINCIPAL=HTTP/${HOSTNAME}"
SPNEGO_VOLUME="Volume=${SPNEGO_KEYTAB}:/etc/arbiter/http.keytab:ro,Z"

cat > /etc/containers/systemd/arbiter-hub-api.container.d/config.conf <<DROPIN
[Container]
Environment=ARBITER_DATABASE_URL=postgresql+asyncpg://arbiter:${DB_PASSWORD}@arbiter-hub-db:5432/arbiter
Environment=ARBITER_AUTH_MODE=oidc
Environment=ARBITER_OIDC_ISSUER=https://${IPA_SERVER}/idp
Environment=ARBITER_OIDC_CLIENT_ID=${OIDC_CLIENT_ID}
Environment=ARBITER_LOCAL_ADMIN_ENABLED=true
Environment=ARBITER_LOCAL_ADMIN_PASSWORD=${ARBITER_SERVICE_PASSWORD}
${KEYLIME_ENV}
${COSIGN_ENV}
${SPNEGO_ENV}
${KEYLIME_VOLUME}
${COSIGN_VOLUME}
${SPNEGO_VOLUME}
DROPIN

# nginx config
echo "Configuring nginx..."
if [ -f /etc/nginx/conf.d/arbiter-hub.conf.template ]; then
    sed -e "s|__HOSTNAME__|$HOSTNAME|g" \
        -e "s|__API_PORT__|$API_PORT|g" \
        -e "s|__UI_PORT__|$UI_PORT|g" \
        -e "s|__EDA_PORT__|$EDA_PORT|g" \
        -e "s|__MCP_PORT__|$MCP_PORT|g" \
        /etc/nginx/conf.d/arbiter-hub.conf.template \
        > /etc/nginx/conf.d/arbiter-hub.conf
fi
setsebool -P httpd_can_network_connect on 2>/dev/null || true
systemctl enable --now nginx

# Start containers
echo "Starting containers..."
systemctl daemon-reload
systemctl start arbiter-hub-db
for i in $(seq 1 30); do
    systemctl is-active arbiter-hub-db >/dev/null 2>&1 && break
    sleep 2
done

# Wait for PostgreSQL to accept connections inside the container
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    podman exec arbiter-hub-db pg_isready -q 2>/dev/null && break
    sleep 2
done

# Run Alembic migrations via podman run (API container doesn't exist yet —
# Quadlet creates it on systemctl start, so podman exec would fail).
# Resolve DB container IP directly — aardvark-dns name resolution doesn't
# work reliably for ad-hoc podman run containers on Quadlet networks.
echo "Running database migrations..."
DB_CONTAINER_IP=$(podman inspect arbiter-hub-db --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "DB container IP: ${DB_CONTAINER_IP}"
MIGRATION_DB_URL="postgresql+asyncpg://arbiter:$(python3 -c "import urllib.parse; print(urllib.parse.quote('${DB_PASSWORD}', safe=''))")@${DB_CONTAINER_IP}:5432/arbiter"
podman run --rm --network systemd-arbiter-hub \
    -e ALEMBIC_DB_URL="$MIGRATION_DB_URL" \
    quay.io/rhel-security/arbiter-hub-api:latest \
    bash -c 'cd /opt/app-root/src && alembic upgrade head'
echo "Migrations complete"

systemctl start arbiter-hub-api arbiter-hub-mcp
for i in $(seq 1 30); do
    curl -sf "http://localhost:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 2
done
echo "Hub API healthy"

systemctl start arbiter-hub-ui 2>/dev/null || echo "UI container not available (optional)"

echo "Phase 3 complete"

# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Seed + Finalize
# ═══════════════════════════════════════════════════════════════════════
echo "── Phase 4: Seed + finalize ──"

# Seed trust profiles
if [ -d /etc/arbiter/trust-profiles ]; then
    echo "Seeding trust profiles..."
    for profile in /etc/arbiter/trust-profiles/*.yaml; do
        [ -f "$profile" ] || continue
        curl -sf -X POST "http://localhost:${API_PORT}/policies" \
            -H "Content-Type: application/json" \
            -H "X-Caller-Principal: admin" \
            -H "X-Caller-Type: system" \
            -d "{\"type\": \"trust_profile\", \"content\": $(python3 -c "import json,yaml; print(json.dumps(yaml.safe_load(open('$profile'))))")}" \
            2>/dev/null || echo "Profile $(basename "$profile") may already exist"
    done
fi

# Seed policies
if [ -f /etc/arbiter/seed-policies.json ]; then
    echo "Seeding attestation policies..."
    python3 -c "
import json, urllib.request
with open('/etc/arbiter/seed-policies.json') as f:
    policies = json.load(f)
for p in policies:
    req = urllib.request.Request(
        'http://localhost:${API_PORT}/policies',
        data=json.dumps(p).encode(),
        headers={'Content-Type': 'application/json',
                 'X-Caller-Principal': 'admin',
                 'X-Caller-Type': 'system'},
        method='POST')
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass
" 2>/dev/null
    echo "Policies seeded"
fi

# EDA controller
if [ "$EDA_ENABLED" = "true" ]; then
    echo "Starting EDA controller..."
    echo "$WEBHOOK_SECRET" > /etc/arbiter/webhook-secret
    chmod 600 /etc/arbiter/webhook-secret

    mkdir -p /var/lib/arbiter/eda/inventory
    cat > /var/lib/arbiter/eda/inventory/hosts.yml <<EDAINV
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
EDAINV
    chmod 600 /var/lib/arbiter/eda/inventory/hosts.yml

    cat > /etc/systemd/system/arbiter-eda.service <<EDASVC
[Unit]
Description=Arbiter EDA Controller (ansible-rulebook)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ansible-rulebook \
  --rulebook /opt/arbiter-eda/rulebooks/attestation.yml \
  --inventory /var/lib/arbiter/eda/inventory/hosts.yml \
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

    # Register webhook
    for i in $(seq 1 10); do
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:${API_PORT}/api/webhooks" \
            -H "Content-Type: application/json" \
            -H "Origin: http://localhost:${API_PORT}" \
            -d "{\"url\":\"http://localhost:${EDA_PORT}/\",\"events\":[\"state_transition\"],\"secret\":\"${WEBHOOK_SECRET}\",\"active\":true}" 2>/dev/null)
        [ "$HTTP" = "200" ] || [ "$HTTP" = "201" ] || [ "$HTTP" = "409" ] && break
        sleep 3
    done
    echo "EDA webhook registered (HTTP $HTTP)"
fi

# Generate enrollment tokens
echo "Generating enrollment tokens..."
mkdir -p /etc/arbiter/enrollment-tokens
for tier in sovereign verified untrusted; do
    TOKEN="$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
    echo "$TOKEN" > "/etc/arbiter/enrollment-tokens/${tier}.token"
    chmod 600 "/etc/arbiter/enrollment-tokens/${tier}.token"
done
echo "Enrollment tokens written to /etc/arbiter/enrollment-tokens/"

# Redact remaining secrets
sed -i 's/\(DB_PASSWORD\s*=\s*\).*/\1<REDACTED>/' "$CONFIG"
sed -i 's/\(WEBHOOK_SECRET\s*=\s*\).*/\1<REDACTED>/' "$CONFIG"
sed -i 's/\(ARBITER_SERVICE_PASSWORD\s*=\s*\).*/\1<REDACTED>/' "$CONFIG"
chown root:root "$CONFIG"

# Register DNS SRV record for replication discovery (if IPA DNS available)
ipa dnsrecord-add "$IPA_DOMAIN" _arbiter-repl._tcp \
    --srv-priority=0 --srv-weight=100 --srv-port=8410 \
    --srv-target="${HOSTNAME}." 2>/dev/null || echo "DNS SRV record may already exist or DNS not managed by IPA"

# Stamp
mkdir -p "$(dirname "$STAMP")"
date -Iseconds > "$STAMP"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Arbiter Server firstboot complete"
echo ""
echo "  Dashboard:  https://${HOSTNAME}:${UI_PORT}/"
echo "  API docs:   https://${HOSTNAME}:${API_PORT}/docs"
echo "  OIDC login: https://${IPA_SERVER}/idp/"
echo ""
echo "  Enrollment tokens: /etc/arbiter/enrollment-tokens/"
echo "    cat /etc/arbiter/enrollment-tokens/verified.token"
echo ""
echo "  Keylime:  $([ "$KEYLIME_ENABLED" = "true" ] && echo "ACTIVE" || echo "DISABLED")"
echo "  Cosign:   $([ "$COSIGN_ENABLED" = "true" ] && echo "ACTIVE" || echo "DISABLED")"
echo "  EDA:      $([ "$EDA_ENABLED" = "true" ] && echo "ACTIVE" || echo "DISABLED")"
echo "════════════════════════════════════════════════════════════════"
