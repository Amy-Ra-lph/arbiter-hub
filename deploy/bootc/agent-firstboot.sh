#!/usr/bin/env bash
# Arbiter Hub agent node firstboot — runs once after bootc image deploys
# Enrolls IPA client, configures Keylime agent, deploys demo workloads, registers with Hub
set -euo pipefail

STAMP="/var/lib/arbiter-hub/.agent-firstboot-complete"
CONFIG="/etc/arbiter-hub/config.env"
LOG="/var/log/arbiter-agent-firstboot.log"

[ -f "$STAMP" ] && { echo "Already provisioned, skipping"; exit 0; }

exec > >(tee -a "$LOG") 2>&1
echo "=== Arbiter Agent firstboot: $(date -Iseconds) ==="

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found — inject via cloud-init userdata"
    exit 1
fi
source "$CONFIG"

: "${IPA_DOMAIN:?Set IPA_DOMAIN in config.env}"
: "${IPA_ADMIN_PASSWORD:?Set IPA_ADMIN_PASSWORD in config.env}"
HOSTNAME="${AGENT_HOSTNAME:-$(hostname -f)}"
IDM_HOST="${IDM_HOSTNAME:?Set IDM_HOSTNAME in config.env}"
HUB_HOST="${HUB_HOSTNAME:?Set HUB_HOSTNAME in config.env}"
HUB_API="${HUB_API_URL:-https://${HUB_HOST}}"

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

# Step 2: Keylime agent config
echo "Configuring Keylime agent..."
REGISTRAR_IP="${IDM_HOST}"
KEYLIME_CONF="/etc/keylime/agent.conf"

if [ -f "$KEYLIME_CONF" ]; then
    sed -i "s|^registrar_ip.*|registrar_ip = ${REGISTRAR_IP}|" "$KEYLIME_CONF"
fi

# swtpm socket for virtual TPM (lab/demo — production uses hardware TPM)
if [ -S /var/run/swtpm-sock ] || command -v swtpm &>/dev/null; then
    echo "Virtual TPM detected, configuring swtpm..."
    mkdir -p /var/lib/swtpm-localca
    swtpm_setup --tpmstate /var/lib/swtpm-localca --tpm2 --createek --create-ek-cert --create-platform-cert 2>/dev/null || true

    cat > /etc/systemd/system/swtpm-agent.service <<SWTPM
[Unit]
Description=Software TPM for Keylime agent
Before=keylime_agent.service

[Service]
Type=simple
ExecStart=/usr/bin/swtpm socket --tpmstate dir=/var/lib/swtpm-localca --tpm2 --ctrl type=tcp,port=2322 --server type=tcp,port=2321
Restart=on-failure

[Install]
WantedBy=multi-user.target
SWTPM
    systemctl daemon-reload
    systemctl enable --now swtpm-agent
fi

systemctl enable --now keylime_agent

# Step 3: Falco configuration
echo "Configuring Falco..."
if [ -f /etc/falco/falco.yaml ]; then
    sed -i 's|^json_output:.*|json_output: true|' /etc/falco/falco.yaml
    sed -i 's|^json_include_output_property:.*|json_include_output_property: true|' /etc/falco/falco.yaml
fi
systemctl enable --now falco-modern-bpf

# Step 4: Canary SSH key (needs runtime entropy, can't bake in image)
echo "Generating canary SSH key..."
mkdir -p /root/.ssh
ssh-keygen -t ed25519 -f /root/.ssh/id_canary -N "" -C "DEMO-CANARY-DO-NOT-USE" 2>/dev/null || true
chmod 600 /root/.ssh/id_canary

# Step 5: Demo workload containers
echo "Starting demo workload containers..."
podman run -d --name governed-agent \
    --restart=always \
    -e HUB_API="${HUB_API}" \
    -e AGENT_NAME="governed-${HOSTNAME}" \
    -v /opt/demo/agents:/app:ro,Z \
    docker.io/library/python:3.12-slim \
    python3 /app/governed_agent.py 2>/dev/null || echo "governed-agent container may already exist"

# Step 6: Authenticate to Hub API
# Auth cascade: Kerberos SPNEGO (IPA keytab) → password fallback
echo "Authenticating to Arbiter Hub..."
AUTH_METHOD="none"
TOKEN=""

hub_api_auth() {
    # Try 1: Kerberos SPNEGO via host keytab (zero shared secrets)
    if [ -f /etc/krb5.keytab ]; then
        echo "Attempting Kerberos SPNEGO auth..."
        kinit -k -t /etc/krb5.keytab "host/$HOSTNAME" 2>/dev/null
        if klist -s 2>/dev/null; then
            TOKEN=$(curl -sk --negotiate -u : -X POST "${HUB_API}/auth/negotiate" \
                2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
            if [ -n "$TOKEN" ]; then
                AUTH_METHOD="spnego"
                echo "SPNEGO auth succeeded"
                return 0
            fi
            echo "SPNEGO auth failed or not supported by Hub API — falling back to password"
        fi
    fi

    # Try 2: Password auth (for non-IPA setups or Hub API without SPNEGO)
    if [ -n "${ARBITER_SERVICE_PASSWORD:-}" ]; then
        echo "Attempting password auth..."
        TOKEN=$(curl -sk -X POST "${HUB_API}/auth/local" \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"admin\",\"password\":\"${ARBITER_SERVICE_PASSWORD}\"}" \
            2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
        if [ -n "$TOKEN" ]; then
            AUTH_METHOD="password"
            echo "Password auth succeeded"
            return 0
        fi
        echo "Password auth failed"
    fi

    echo "No auth method succeeded"
    return 1
}

# Step 7: Register workloads with Hub API
echo "Registering workloads with Arbiter Hub..."
for i in $(seq 1 20); do
    HTTP=$(curl -sk -o /dev/null -w "%{http_code}" "${HUB_API}/health" 2>/dev/null)
    [ "$HTTP" = "200" ] && break
    echo "Waiting for Hub API... ($i/20)"
    sleep 5
done

if [ "$HTTP" = "200" ]; then
    if hub_api_auth; then
        curl -sk -X POST "${HUB_API}/api/workloads" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${TOKEN}" \
            -d "{
                \"name\": \"agent-${HOSTNAME}\",
                \"hostname\": \"${HOSTNAME}\",
                \"workload_type\": \"host\",
                \"attestation_types\": [\"keylime\"],
                \"metadata\": {\"role\": \"agent\", \"falco\": true}
            }" 2>/dev/null || echo "Workload registration may need manual completion"
        echo "Workload registered (auth=$AUTH_METHOD)"
    else
        echo "Auth failed — workload registration deferred to manual step"
    fi
else
    echo "Hub API not reachable — workload registration deferred to manual step"
fi

mkdir -p "$(dirname "$STAMP")"
date -Iseconds > "$STAMP"
echo "=== Agent firstboot complete: $(date -Iseconds) ==="
