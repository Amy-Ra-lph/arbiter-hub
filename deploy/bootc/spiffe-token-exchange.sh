#!/usr/bin/env bash
# spiffe-token-exchange — exchange a SPIRE JWT SVID for an ahdapa OAuth2 token
# Uses RFC 8693 token exchange: workload proves SPIFFE identity, gets IPA-backed OAuth2 token
#
# Usage: spiffe-token-exchange.sh [audience]
# Requires: spire-agent running, SPIRE Workload API socket accessible
#
# Flow:
#   1. Fetch JWT SVID from SPIRE Agent Workload API
#   2. POST to ahdapa token exchange endpoint (RFC 8693)
#   3. Receive OAuth2 access token bound to IPA service principal
#   4. Output token to stdout (pipe-friendly)
set -euo pipefail

AUDIENCE="${1:-https://idm.arbiter.demo/idp}"
CLIENT_ID="${AHDAPA_CLIENT_ID:-arbiter-hub}"
AHDAPA_URL="${AHDAPA_FEDERATION_URL:-https://idm.arbiter.demo/idp/federation/token}"
SPIRE_SOCKET="${SPIRE_AGENT_SOCKET:-/tmp/spire-agent/public/api.sock}"

# Step 1: Get JWT SVID from SPIRE Agent
# spire-agent api fetch jwt returns the token on stdout
JWT_SVID=$(spire-agent api fetch jwt \
    -audience "$AUDIENCE" \
    -socketPath "$SPIRE_SOCKET" \
    -output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
svids = data.get('svids', data if isinstance(data, list) else [data])
if svids:
    print(svids[0].get('svid', svids[0].get('token', '')))
" 2>/dev/null)

if [ -z "$JWT_SVID" ]; then
    echo "ERROR: Failed to fetch JWT SVID from SPIRE Agent" >&2
    echo "Is spire-agent running? Socket: $SPIRE_SOCKET" >&2
    exit 1
fi

SPIFFE_ID=$(python3 -c "
import json, base64, sys
parts = '$JWT_SVID'.split('.')
payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
print(payload.get('sub', 'unknown'))
" 2>/dev/null)

echo "SPIFFE ID: $SPIFFE_ID" >&2
echo "Audience:  $AUDIENCE" >&2

# Step 2: Exchange JWT SVID for OAuth2 token via ahdapa /federation/token
# HTTP Basic Auth: username=client_id, password=JWT SVID
RESPONSE=$(curl -sk -u "${CLIENT_ID}:${JWT_SVID}" \
    -X POST "$AHDAPA_URL" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "" \
    2>/dev/null)

# Step 3: Extract access token
ACCESS_TOKEN=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'access_token' in data:
    print(data['access_token'])
elif 'error' in data:
    print(f\"ERROR: {data['error']} — {data.get('error_description', '')}\", file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "ERROR: Token exchange failed" >&2
    echo "Response: $RESPONSE" >&2
    exit 1
fi

echo "Exchange:  SPIFFE SVID → OAuth2 access token" >&2
echo "$ACCESS_TOKEN"
