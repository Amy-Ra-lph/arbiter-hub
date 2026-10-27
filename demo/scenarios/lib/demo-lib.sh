#!/usr/bin/env bash
# Shared demo functions for Arbiter Hub persona demos

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Env defaults
HUB_URL="${ARBITER_HUB_URL:-https://hub.arbiter.demo:8400}"
API_URL="${HUB_URL}/api"
IDP_URL="${ARBITER_IDP_URL:-https://idm.arbiter.demo/idp}"
IPA_REALM="${ARBITER_REALM:-ARBITER.DEMO}"
DOMAIN="${ARBITER_DOMAIN:-arbiter.demo}"
IDM_HOST="${ARBITER_IDM_HOST:-idm.arbiter.demo}"
HUB_HOST="${ARBITER_HUB_HOST:-hub.arbiter.demo}"
AGENT_HOST="${ARBITER_AGENT_HOST:-agent.arbiter.demo}"
SSH_KEY="${ARBITER_SSH_KEY:-$HOME/.ssh/idm_ci_key}"
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -o IdentitiesOnly=yes"
CLIENT_SECRET="${ARBITER_CLIENT_SECRET:?Set ARBITER_CLIENT_SECRET before running}"
ENFORCEMENT_MCP="${ARBITER_ENFORCEMENT_MCP_URL:-http://hub.arbiter.demo:8402}"
PAUSE="${DEMO_PAUSE:-3}"
AUTO_MODE=false

# Parse common args
for arg in "$@"; do
    case "$arg" in
        --auto) AUTO_MODE=true; PAUSE=1 ;;
    esac
done

# Display functions
banner() {
    echo ""
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}${BOLD}  $1${NC}"
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

act() {
    echo ""
    echo -e "${MAGENTA}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${MAGENTA}${BOLD}  ACT $1: $2${NC}"
    echo -e "${MAGENTA}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

step()  { echo -e "${GREEN}▸${NC} ${BOLD}$1${NC}"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "${RED}✗${NC} $1"; }
note()  { echo -e "${DIM}  $1${NC}"; }

pause() {
    if $AUTO_MODE; then
        sleep "$PAUSE"
    else
        echo -e "${YELLOW}[press Enter to continue]${NC}"
        read -r
    fi
}

talking_point() {
    echo -e "${CYAN}💬 $1${NC}"
}

# API functions
get_token() {
    curl -sk -X POST "${IDP_URL}/token" \
        -u "arbiter-hub:${CLIENT_SECRET}" \
        -d "grant_type=client_credentials" \
        -d "scope=openid $1" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

get_token_password() {
    local user="$1" pass="$2" scopes="$3"
    curl -sk -X POST "${IDP_URL}/oauth2/token" \
        -d "grant_type=password" \
        -d "username=${user}" \
        -d "password=${pass}" \
        -d "client_id=arbiter-hub" \
        -d "scope=${scopes}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

api_call() {
    local method="$1" path="$2" token="$3"
    shift 3
    curl -sk -X "$method" "${API_URL}${path}" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        "$@"
}

ssh_cmd() {
    local host="$1"; shift
    ssh $SSH_OPTS -i "$SSH_KEY" root@"$host" "$@" 2>/dev/null
}

mcp_call() {
    local tool="$1"; shift
    curl -sk -X POST "$ENFORCEMENT_MCP" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":{$*}}}"
}

# Workload helpers
list_workloads() {
    local token="$1"
    api_call GET "/workloads?count=100" "$token" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Total: {data.get(\"total\", 0)} workloads\n')
for w in data.get('items', []):
    state = w['current_state']
    icon = '🟢' if state == 'healthy' else ('🔴' if state in ('failed','revoked') else '🟡')
    backends = ', '.join(w.get('backend_types', []))
    tier = w.get('metadata', {}).get('trust_tier', '')
    tier_str = f' [{tier}]' if tier else ''
    print(f'  {icon} {w[\"display_name\"]:.<40s} {state:<12s}{tier_str}')
" 2>/dev/null
}

show_audit() {
    local token="$1" count="${2:-10}"
    api_call GET "/audit?count=${count}" "$token" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data.get('items', []):
    ts = e.get('created_at', e.get('timestamp',''))[:19]
    print(f'  {ts} | {e.get(\"actor\",\"-\"):.<25s} | {e.get(\"action\",\"-\"):<18s} | {e.get(\"target_type\",\"-\")}')
" 2>/dev/null
}

# Cleanup tracker
CREATED_WORKLOAD_IDS=()
track_workload() { CREATED_WORKLOAD_IDS+=("$1"); }

cleanup_workloads() {
    local token="$1"
    if [ ${#CREATED_WORKLOAD_IDS[@]} -gt 0 ]; then
        step "Cleaning up ${#CREATED_WORKLOAD_IDS[@]} demo workload(s)"
        for wid in "${CREATED_WORKLOAD_IDS[@]}"; do
            api_call DELETE "/workloads/${wid}" "$token" >/dev/null 2>&1 || true
            ok "Removed $wid"
        done
    fi
}

demo_summary() {
    echo ""
    banner "$1 — COMPLETE"
    echo -e "${BOLD}Summary:${NC}"
}
