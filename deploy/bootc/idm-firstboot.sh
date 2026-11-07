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

# ── ahdapa OAuth2/OIDC Configuration ────────────────────────────────
if command -v ahdapactl &>/dev/null; then
    echo "Configuring ahdapa OIDC provider..."

    # Wait for ahdapa to be running (IPA installer enables it)
    for i in $(seq 1 30); do
        ipactl status 2>/dev/null | grep -q "ahdapa Service: RUNNING" && break
        sleep 2
    done

    # CORS config for browser OIDC token exchange
    if [ ! -f /etc/httpd/conf.d/ipa-idp-cors.conf ]; then
        cat > /etc/httpd/conf.d/ipa-idp-cors.conf <<'CORS'
<Location /idp>
    Header always set Access-Control-Allow-Origin "*"
    Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
    Header always set Access-Control-Allow-Headers "Authorization, Content-Type, Accept"
    Header always set Access-Control-Max-Age "3600"
</Location>
CORS
        echo "CORS config deployed"
    fi

    # OPTIONS preflight in idp proxy
    if [ -f /etc/httpd/conf.d/ipa-idp-proxy.conf ]; then
        if ! grep -q "RewriteCond.*OPTIONS" /etc/httpd/conf.d/ipa-idp-proxy.conf 2>/dev/null; then
            sed -i '/Require all granted/a\    RewriteEngine On\n    RewriteCond %{REQUEST_METHOD} =OPTIONS\n    RewriteRule .* - [R=204,L]' \
                /etc/httpd/conf.d/ipa-idp-proxy.conf
            echo "OPTIONS preflight added to idp proxy"
        fi
    fi

    systemctl reload httpd 2>/dev/null || true

    # Register OAuth2 clients from config.env if provided
    if [ -n "${AHDAPA_CLIENT_ID:-}" ] && [ -n "${AHDAPA_CLIENT_SECRET:-}" ]; then
        echo "Registering OAuth2 client: ${AHDAPA_CLIENT_ID}"
        echo "$IPA_ADMIN_PASSWORD" | kinit admin 2>/dev/null || true
        ahdapactl login "https://${HOSTNAME}/idp" --kerberos --insecure 2>/dev/null || true

        CLIENTS_TOML="/etc/ahdapa/clients.toml"
        if ! grep -q "client_id.*=.*\"${AHDAPA_CLIENT_ID}\"" "$CLIENTS_TOML" 2>/dev/null; then
            REDIRECT_URI="${AHDAPA_REDIRECT_URI:-https://${AHDAPA_CLIENT_ID}/auth/callback}"
            cat >> "$CLIENTS_TOML" <<CLIENT

[[client]]
client_id                  = "${AHDAPA_CLIENT_ID}"
client_name                = "${AHDAPA_CLIENT_NAME:-${AHDAPA_CLIENT_ID}}"
client_secret              = "${AHDAPA_CLIENT_SECRET}"
token_endpoint_auth_method = "client_secret_basic"
scopes                     = ${AHDAPA_SCOPES:-["openid", "profile"]}
grant_types                = ["authorization_code", "client_credentials", "urn:ietf:params:oauth:grant-type:token-exchange"]
redirect_uris              = ["${REDIRECT_URI}", "${REDIRECT_URI%/callback}/"]
skip_consent               = true
allow_token_exchange_actor  = true
CLIENT
            echo "OAuth2 client registered in clients.toml"
            systemctl restart ahdapa 2>/dev/null || true
        fi
    fi

    # Federation config if SPIFFE trust domain specified
    if [ -n "${SPIFFE_TRUST_DOMAIN:-}" ]; then
        SPIRE_ISSUER="https://${HOSTNAME}/spire"
        echo "Configuring SPIFFE federation: trust_domain=${SPIFFE_TRUST_DOMAIN}"

        AHDAPA_TOML="/etc/ahdapa/ahdapa.toml"
        if ! grep -q '\[federation\]' "$AHDAPA_TOML" 2>/dev/null; then
            cat >> "$AHDAPA_TOML" <<FEDERATION

[federation]
trusted_issuers     = ["${SPIRE_ISSUER}"]
trust_anchors       = []
max_clock_skew_secs = 30
FEDERATION
            echo "Federation section added to ahdapa.toml"
            systemctl restart ahdapa 2>/dev/null || true
        fi

        # Add allowed_token_exchange_audiences to client if registered
        if [ -n "${AHDAPA_CLIENT_ID:-}" ]; then
            CLIENTS_TOML="/etc/ahdapa/clients.toml"
            if ! grep -q "allowed_token_exchange_audiences" "$CLIENTS_TOML" 2>/dev/null; then
                sed -i "/client_id.*=.*\"${AHDAPA_CLIENT_ID}\"/,/^$/{
                    /allow_token_exchange_actor/a\\
allowed_token_exchange_audiences = [\"${SPIRE_ISSUER}\"]
                }" "$CLIENTS_TOML"
                systemctl restart ahdapa 2>/dev/null || true
            fi
        fi

        # Create Identity HBAC rule for federation token exchange
        ahdapactl login "https://${HOSTNAME}/idp" --kerberos --insecure 2>/dev/null || true
        ahdapactl hbac create \
            --name "federation-token-exchange" \
            --enabled true \
            --user-category true --client-category true --scope-category true \
            --network-category true --device-category true --mfa-bypass true \
            --delegation-target-category true 2>/dev/null || echo "HBAC rule may already exist"
    fi

    echo "ahdapa OIDC provider configured"
fi

mkdir -p "$(dirname "$STAMP")"
date -Iseconds > "$STAMP"
echo "=== IdM firstboot complete: $(date -Iseconds) ==="
