#!/usr/bin/env bash
# openshell-sandbox-deploy.sh — Deploy OpenShell gateway + trust-tiered sandboxes
#
# Podman-native deployment that bypasses the OpenShell CLI for sandbox creation.
# The CLI's sandbox create requires the gateway to mint JWT tokens, but the
# gateway's JWT signing-key auto-discovery is Kubernetes-only (v0.0.111).
# This script creates sandbox containers directly and registers them as
# Arbiter Hub workloads.
#
# Usage:
#   ./scripts/openshell-sandbox-deploy.sh [--arbiter-hub-url URL] [--sandbox-image IMAGE]
#
# Requires: podman, curl, jq
set -euo pipefail

GATEWAY_IMAGE="${OPENSHELL_GATEWAY_IMAGE:-quay.io/rhel-security/poc-openshell-rhhi:gateway-0.0.111}"
SANDBOX_IMAGE="${OPENSHELL_SANDBOX_IMAGE:-registry.access.redhat.com/ubi10/ubi:latest}"
ARBITER_HUB_URL="${ARBITER_HUB_URL:-}"
PKI_DIR="/etc/openshell/pki"
HEALTH_PORT=17672

# Trust tier definitions: name, memory, cpu, read-only, SELinux type
declare -A TIER_MEMORY=([sovereign]=1g [verified]=512m [untrusted]=256m)
declare -A TIER_CPU=([sovereign]=2 [verified]=1 [untrusted]=1)
declare -A TIER_READONLY=([sovereign]=false [verified]=false [untrusted]=true)

usage() {
    echo "Usage: $0 [--arbiter-hub-url URL] [--sandbox-image IMAGE]"
    echo ""
    echo "Environment variables:"
    echo "  OPENSHELL_GATEWAY_IMAGE  Gateway image (default: quay.io/.../gateway-0.0.111)"
    echo "  OPENSHELL_SANDBOX_IMAGE  Sandbox base image (default: UBI 10)"
    echo "  ARBITER_HUB_URL         Arbiter Hub API URL for workload registration"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arbiter-hub-url) ARBITER_HUB_URL="$2"; shift 2 ;;
        --sandbox-image)   SANDBOX_IMAGE="$2"; shift 2 ;;
        -h|--help)         usage ;;
        *)                 echo "Unknown option: $1"; usage ;;
    esac
done

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# --- Step 1: Generate PKI ---
generate_pki() {
    if [[ -f "$PKI_DIR/server/tls.crt" ]]; then
        log "PKI already exists at $PKI_DIR, skipping generation"
        return 0
    fi

    log "Generating OpenShell PKI..."
    local hostname
    hostname=$(hostname -f)

    mkdir -p "$PKI_DIR"
    local tmpdir
    tmpdir=$(mktemp -d)
    chmod 777 "$tmpdir"

    podman run --rm --user root \
        -v "$tmpdir:/output:Z" \
        "$GATEWAY_IMAGE" \
        generate-certs --output-dir /output \
        --server-san "$hostname" \
        --server-san localhost \
        --server-san "$(hostname -I | awk '{print $1}')"

    cp -a "$tmpdir"/* "$PKI_DIR/"
    rm -rf "$tmpdir"
    log "PKI generated at $PKI_DIR"
}

# --- Step 2: Enable podman socket ---
enable_podman_socket() {
    if ! systemctl is-active --quiet podman.socket; then
        log "Enabling podman.socket..."
        systemctl enable --now podman.socket
    fi
}

# --- Step 3: Deploy gateway ---
deploy_gateway() {
    if podman ps --filter name=openshell-gateway --format '{{.Names}}' | grep -q openshell-gateway; then
        log "Gateway already running"
        return 0
    fi

    podman rm -f openshell-gateway 2>/dev/null || true

    log "Starting OpenShell gateway..."
    podman run -d \
        --name openshell-gateway \
        --network host \
        --user root \
        --security-opt label=disable \
        -v /run/podman/podman.sock:/run/podman/podman.sock \
        -v "$PKI_DIR:$PKI_DIR:ro" \
        -e OPENSHELL_BIND_ADDRESS=0.0.0.0 \
        -e OPENSHELL_HEALTH_PORT=$HEALTH_PORT \
        -e OPENSHELL_LOG_LEVEL=info \
        -e OPENSHELL_DRIVERS=podman \
        -e OPENSHELL_PODMAN_SOCKET=/run/podman/podman.sock \
        -e OPENSHELL_DISABLE_TLS=true \
        "$GATEWAY_IMAGE"

    # Wait for health
    local attempt
    for attempt in $(seq 1 15); do
        if curl -sf "http://localhost:$HEALTH_PORT/healthz" >/dev/null 2>&1; then
            log "Gateway healthy"
            return 0
        fi
        sleep 2
    done
    log "WARNING: Gateway health check did not pass within 30s"
}

# --- Step 4: Create trust-tiered sandboxes ---
create_sandbox() {
    local tier="$1"
    local name="wid-${tier}"
    local memory="${TIER_MEMORY[$tier]}"
    local cpus="${TIER_CPU[$tier]}"
    local readonly="${TIER_READONLY[$tier]}"

    if podman ps --filter "name=^${name}$" --format '{{.Names}}' | grep -q "^${name}$"; then
        log "Sandbox $name already running"
        return 0
    fi

    podman rm -f "$name" 2>/dev/null || true

    local -a run_args=(
        -d
        --name "$name"
        --hostname "${name}.arbiter.demo"
        --memory "$memory"
        --cpus "$cpus"
        --label io.arbiter.trust-tier="$tier"
        --label io.arbiter.workload-name="$name"
        --label io.openshell.managed=true
    )

    if [[ "$readonly" == "true" ]]; then
        run_args+=(--read-only --tmpfs /tmp:rw,size=64m)
    fi

    log "Creating sandbox: $name (tier=$tier, memory=$memory, cpu=$cpus)"
    podman run "${run_args[@]}" "$SANDBOX_IMAGE" \
        /bin/bash -c 'while true; do sleep 3600; done'
}

create_all_sandboxes() {
    for tier in sovereign verified untrusted; do
        create_sandbox "$tier"
    done
}

# --- Step 5: Register workloads in Arbiter Hub ---
register_workload() {
    local name="$1"
    local tier="$2"
    local url="$ARBITER_HUB_URL"

    if [[ -z "$url" ]]; then
        log "ARBITER_HUB_URL not set, skipping workload registration for $name"
        return 0
    fi

    local workload_type="sandbox"
    local container_id
    container_id=$(podman inspect "$name" --format '{{.Id}}' 2>/dev/null | head -c 12)

    local payload
    payload=$(cat <<EOF
{
    "ipa_principal": "openshell/${name}@ARBITER.DEMO",
    "display_name": "OpenShell Sandbox: ${name}",
    "workload_type": "${workload_type}",
    "backend_types": ["FALCO"],
    "metadata": {
        "trust_tier": "${tier}",
        "container_id": "${container_id}",
        "container_name": "${name}",
        "sandbox_image": "${SANDBOX_IMAGE}",
        "managed_by": "openshell-sandbox-deploy"
    }
}
EOF
)

    local http_code
    http_code=$(curl -s -o /dev/null -w '%{http_code}' \
        -X POST "$url/workloads" \
        -H 'Content-Type: application/json' \
        -d "$payload")

    case "$http_code" in
        200|201) log "Registered workload: $name (tier=$tier)" ;;
        409)     log "Workload $name already registered" ;;
        *)       log "WARNING: Registration failed for $name (HTTP $http_code)" ;;
    esac
}

register_all_workloads() {
    for tier in sovereign verified untrusted; do
        register_workload "wid-${tier}" "$tier"
    done
}

# --- Main ---
main() {
    log "=== OpenShell Podman Deployment ==="
    log "Gateway image: $GATEWAY_IMAGE"
    log "Sandbox image: $SANDBOX_IMAGE"
    [[ -n "$ARBITER_HUB_URL" ]] && log "Arbiter Hub: $ARBITER_HUB_URL"

    generate_pki
    enable_podman_socket
    deploy_gateway
    create_all_sandboxes
    register_all_workloads

    log ""
    log "=== Deployment Summary ==="
    echo "Gateway:  $(podman ps --filter name=openshell-gateway --format '{{.Names}}  {{.Status}}')"
    echo "Sandboxes:"
    podman ps --filter label=io.openshell.managed=true --format '  {{.Names}}  {{.Status}}  memory={{.Size}}'

    if [[ -n "$ARBITER_HUB_URL" ]]; then
        echo ""
        echo "Arbiter Hub workloads:"
        curl -s "$ARBITER_HUB_URL/workloads" | \
            python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    meta = w.get('metadata', {})
    if meta.get('managed_by') == 'openshell-sandbox-deploy':
        print(f\"  {w['display_name']}  state={w['current_state']}  tier={meta.get('trust_tier', '?')}\")
" 2>/dev/null || true
    fi

    log ""
    log "NOTE: Sandbox JWT auth requires Kubernetes. Podman sandboxes are"
    log "created directly until upstream adds OPENSHELL_JWT_SIGNING_KEY_DIR."
    log "Gateway runs TLS-disabled for local demo. Production deployments"
    log "should use Kubernetes with Helm-managed JWT secrets."
}

main "$@"
