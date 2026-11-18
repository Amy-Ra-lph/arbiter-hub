#!/usr/bin/env bash
# MCP access matrix demo: shows each persona's tool access across MCP servers
set -euo pipefail

HUB_URL="${ARBITER_HUB_URL:-https://hub.arbiter.demo}"
API_URL="${HUB_URL}/api"
IDP_URL="${ARBITER_IDP_URL:-https://idm.arbiter.demo/idp}"
AGENT_HOST="${ARBITER_AGENT_HOST:-agent.arbiter.demo}"
ENFORCEMENT_MCP="${ENFORCEMENT_MCP_URL:-http://hub.arbiter.demo:8402}"
LINUX_MCP="${LINUX_MCP_URL:-http://agent.arbiter.demo:8402}"
ARBITER_MCP="${ARBITER_MCP_URL:-http://hub.arbiter.demo:8401}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}${BOLD}  $1${NC}"; echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════${NC}\n"; }
step() { echo -e "${GREEN}▸${NC} ${BOLD}$1${NC}"; }
ok() { echo -e "  ${GREEN}✓${NC} $1"; }
blocked() { echo -e "  ${RED}✗${NC} $1 ${RED}(BLOCKED)${NC}"; }
allowed() { echo -e "  ${GREEN}✓${NC} $1 ${GREEN}(ALLOWED)${NC}"; }

get_token() {
    local user="$1" pass="$2" scopes="$3"
    curl -sk -X POST "${IDP_URL}/oauth2/token" \
        -d "grant_type=password" \
        -d "username=${user}" \
        -d "password=${pass}" \
        -d "client_id=arbiter-hub" \
        -d "scope=${scopes}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

mcp_call() {
    local url="$1" tool="$2" token="$3" args="${4:-{}}"
    local result
    result=$(curl -sk -X POST "${url}/tools/call" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${tool}\", \"arguments\": ${args}}" \
        -w "\n%{http_code}" 2>/dev/null)
    local http_code
    http_code=$(echo "$result" | tail -1)
    local body
    body=$(echo "$result" | sed '$d')
    echo "${http_code}|${body}"
}

api_call() {
    local method="$1" path="$2" token="$3"
    shift 3
    curl -sk -X "$method" "${API_URL}${path}" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -o /dev/null -w "%{http_code}" \
        "$@"
}

test_access() {
    local label="$1" expected="$2" actual="$3"
    if [ "$expected" = "allow" ]; then
        if [ "$actual" = "200" ] || [ "$actual" = "201" ]; then
            allowed "$label"
        else
            echo -e "  ${YELLOW}?${NC} $label — expected allow, got HTTP $actual"
        fi
    else
        if [ "$actual" = "403" ] || [ "$actual" = "401" ]; then
            blocked "$label"
        else
            echo -e "  ${YELLOW}?${NC} $label — expected block, got HTTP $actual"
        fi
    fi
}

###############################################################################
banner "MCP Access Matrix: Per-Persona Tool Access"
###############################################################################

echo -e "${BOLD}Expected access matrix:${NC}"
echo ""
echo "  ┌──────────┬──────────────┬────────────────┬──────────────┬─────────┐"
echo "  │ Persona  │ Arbiter API  │ linux-mcp (19) │ enforce-mcp  │ KBS     │"
echo "  ├──────────┼──────────────┼────────────────┼──────────────┼─────────┤"
echo "  │ Alice    │ Full         │ Full           │ Full         │ R/W     │"
echo "  │ Bob      │ Ops          │ Full           │ Read+Apply   │ —       │"
echo "  │ Carol    │ CI only      │ —              │ —            │ —       │"
echo "  │ Dave     │ Read-only    │ 3 tools        │ Read-only    │ —       │"
echo "  │ Eve      │ Re-attest    │ —              │ —            │ —       │"
echo "  └──────────┴──────────────┴────────────────┴──────────────┴─────────┘"
echo ""

###############################################################################
step "Authenticating all personas"
###############################################################################

ALICE_TOKEN=$(get_token "alice" "redhat123" "openid profile attestation-admin")
ok "Alice (admin)"
BOB_TOKEN=$(get_token "bob" "redhat123" "openid profile attestation-operator")
ok "Bob (operator)"
CAROL_TOKEN=$(get_token "carol" "redhat123" "openid profile attestation-pipeline")
ok "Carol (pipeline)"
DAVE_TOKEN=$(get_token "dave" "redhat123" "openid profile attestation-viewer")
ok "Dave (viewer)"
EVE_TOKEN=$(get_token "eve" "redhat123" "openid profile attestation-agent")
ok "Eve (agent)"

###############################################################################
banner "1. Arbiter Hub API Access"
###############################################################################

for persona in alice bob carol dave eve; do
    step "$persona — Arbiter Hub API"
    eval "TOKEN=\$$(echo ${persona} | tr '[:lower:]' '[:upper:]')_TOKEN"

    # Read workloads (all roles can read)
    code=$(api_call GET "/workloads?count=1" "$TOKEN")
    test_access "GET /workloads" "allow" "$code"

    # Register workload (admin, operator, pipeline)
    code=$(api_call POST "/workloads" "$TOKEN" -d '{
        "ipa_principal": "test/'"${persona}"'-matrix@ARBITER.DEMO",
        "display_name": "Matrix Test '"${persona}"'",
        "workload_type": "service",
        "backend_types": ["keylime"]
    }')
    case "$persona" in
        alice|bob) test_access "POST /workloads (register)" "allow" "$code" ;;
        carol)     test_access "POST /workloads (register)" "allow" "$code" ;;
        *)         test_access "POST /workloads (register)" "block" "$code" ;;
    esac

    # KBS secrets (admin only)
    code=$(api_call GET "/kbs/v0/resources" "$TOKEN")
    case "$persona" in
        alice) test_access "GET /kbs/v0/resources" "allow" "$code" ;;
        *)     test_access "GET /kbs/v0/resources" "block" "$code" ;;
    esac

    # Register webhook (admin only)
    code=$(api_call POST "/api/webhooks" "$TOKEN" -d '{
        "url": "http://test.example.com",
        "events": ["state_transition"],
        "secret": "test"
    }')
    case "$persona" in
        alice) test_access "POST /webhooks (register)" "allow" "$code" ;;
        *)     test_access "POST /webhooks (register)" "block" "$code" ;;
    esac

    echo ""
done

###############################################################################
banner "2. linux-mcp-server Tool Access"
###############################################################################

LINUX_TOOLS=("systemctl_status" "ps_aux" "df_usage" "strace_attach" "tcpdump_capture")

for persona in alice bob carol dave eve; do
    step "$persona — linux-mcp-server"
    eval "TOKEN=\$$(echo ${persona} | tr '[:lower:]' '[:upper:]')_TOKEN"

    for tool in "${LINUX_TOOLS[@]}"; do
        result=$(mcp_call "$LINUX_MCP" "$tool" "$TOKEN" '{}')
        code=$(echo "$result" | cut -d'|' -f1)
        case "$persona" in
            alice|bob)
                test_access "$tool" "allow" "$code"
                ;;
            dave)
                case "$tool" in
                    systemctl_status|ps_aux|df_usage)
                        test_access "$tool (read-only)" "allow" "$code"
                        ;;
                    *)
                        test_access "$tool (privileged)" "block" "$code"
                        ;;
                esac
                ;;
            *)
                test_access "$tool" "block" "$code"
                ;;
        esac
    done
    echo ""
done

###############################################################################
banner "3. enforcement-mcp Tool Access"
###############################################################################

ENFORCE_TOOLS=("selinux_status" "fapolicyd_list_rules" "fapolicyd_add_rule" "aide_check" "mls_get_level")

for persona in alice bob carol dave eve; do
    step "$persona — enforcement-mcp"
    eval "TOKEN=\$$(echo ${persona} | tr '[:lower:]' '[:upper:]')_TOKEN"

    for tool in "${ENFORCE_TOOLS[@]}"; do
        result=$(mcp_call "$ENFORCEMENT_MCP" "$tool" "$TOKEN" '{}')
        code=$(echo "$result" | cut -d'|' -f1)
        case "$persona" in
            alice)
                test_access "$tool" "allow" "$code"
                ;;
            bob)
                case "$tool" in
                    selinux_status|fapolicyd_list_rules|aide_check|mls_get_level)
                        test_access "$tool (read)" "allow" "$code"
                        ;;
                    fapolicyd_add_rule)
                        test_access "$tool (write)" "allow" "$code"
                        ;;
                esac
                ;;
            dave)
                case "$tool" in
                    selinux_status|fapolicyd_list_rules|mls_get_level)
                        test_access "$tool (read-only)" "allow" "$code"
                        ;;
                    *)
                        test_access "$tool (write)" "block" "$code"
                        ;;
                esac
                ;;
            *)
                test_access "$tool" "block" "$code"
                ;;
        esac
    done
    echo ""
done

###############################################################################
banner "4. Arbiter Hub MCP Server Tool Access"
###############################################################################

ARBITER_TOOLS=("list_workloads" "get_workload" "register_workload" "trigger_attestation" "manage_policy")

for persona in alice bob carol dave eve; do
    step "$persona — arbiter-hub-mcp"
    eval "TOKEN=\$$(echo ${persona} | tr '[:lower:]' '[:upper:]')_TOKEN"

    for tool in "${ARBITER_TOOLS[@]}"; do
        result=$(mcp_call "$ARBITER_MCP" "$tool" "$TOKEN" '{}')
        code=$(echo "$result" | cut -d'|' -f1)
        case "$persona" in
            alice)
                test_access "$tool" "allow" "$code"
                ;;
            bob)
                case "$tool" in
                    list_workloads|get_workload|register_workload|trigger_attestation)
                        test_access "$tool" "allow" "$code"
                        ;;
                    manage_policy)
                        test_access "$tool (admin-only)" "block" "$code"
                        ;;
                esac
                ;;
            carol)
                case "$tool" in
                    list_workloads|get_workload|trigger_attestation)
                        test_access "$tool" "allow" "$code"
                        ;;
                    *)
                        test_access "$tool" "block" "$code"
                        ;;
                esac
                ;;
            dave)
                case "$tool" in
                    list_workloads|get_workload)
                        test_access "$tool (read)" "allow" "$code"
                        ;;
                    *)
                        test_access "$tool" "block" "$code"
                        ;;
                esac
                ;;
            eve)
                case "$tool" in
                    list_workloads|get_workload|trigger_attestation)
                        test_access "$tool (agent)" "allow" "$code"
                        ;;
                    *)
                        test_access "$tool" "block" "$code"
                        ;;
                esac
                ;;
        esac
    done
    echo ""
done

###############################################################################
banner "ACCESS MATRIX COMPLETE"
###############################################################################

echo -e "${BOLD}Results:${NC}"
echo "  Each persona was tested against 4 MCP servers with role-appropriate access."
echo "  HBAC rules enforce service-level access at the IPA layer."
echo "  RBAC roles enforce operation-level access at the API layer."
echo "  Together they implement defense-in-depth access control for agentic workloads."

# Clean up matrix test workloads
step "Cleaning up matrix test workloads"
for persona in alice bob carol; do
    CLEANUP_ID=$(curl -sk "${API_URL}/workloads?count=100" \
        -H "Authorization: Bearer ${ALICE_TOKEN}" \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('items', []):
    if 'Matrix Test ${persona}' in w.get('display_name',''):
        print(w['id'])
        break
" 2>/dev/null || true)
    if [ -n "$CLEANUP_ID" ]; then
        api_call DELETE "/workloads/${CLEANUP_ID}" "$ALICE_TOKEN" >/dev/null 2>&1 || true
    fi
done
ok "Test workloads cleaned up"
