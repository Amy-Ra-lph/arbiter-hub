#!/bin/bash
# Checks UI→API proxy health and auto-remediates on failure.
# Deploy as a systemd timer (30s interval) on the hub node.
#
# Remediation ladder:
#   1. nginx reload (fixes DNS cache staleness)
#   2. UI container restart (fixes nginx process issues)
#   3. API container restart (fixes stopped API)
set -euo pipefail

PROXY_URL="${ARBITER_PROXY_URL:-http://localhost:8443/api/health}"
DIRECT_URL="${ARBITER_API_URL:-http://localhost:8400/health}"
UI_CONTAINER="${ARBITER_UI_CONTAINER:-arbiter-hub-ui}"
API_CONTAINER="${ARBITER_API_CONTAINER:-arbiter-hub-api}"

log() { logger -t arbiter-healthcheck "$*"; }

if curl -sf --connect-timeout 3 "$PROXY_URL" >/dev/null 2>&1; then
    exit 0
fi

if curl -sf --connect-timeout 3 "$DIRECT_URL" >/dev/null 2>&1; then
    log "UI→API proxy broken, API alive — reloading nginx"
    podman exec "$UI_CONTAINER" nginx -s reload 2>/dev/null || true
    sleep 2
    if curl -sf --connect-timeout 3 "$PROXY_URL" >/dev/null 2>&1; then
        log "UI→API proxy restored after nginx reload"
    else
        log "nginx reload insufficient — restarting UI container"
        podman restart "$UI_CONTAINER"
    fi
else
    if podman ps -a --filter "name=$API_CONTAINER" --format '{{.Status}}' | grep -qi exited; then
        log "API container exited — restarting"
        podman start "$API_CONTAINER"
        sleep 3
        podman exec "$UI_CONTAINER" nginx -s reload 2>/dev/null || true
    else
        log "API not running and container not found — manual intervention needed"
    fi
fi
