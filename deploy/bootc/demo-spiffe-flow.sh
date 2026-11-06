#!/usr/bin/env bash
# demo-spiffe-flow — demonstrates zero-credential workload authentication
#
# Run on the agent node to show the full chain:
#   SPIRE attestation → JWT SVID → ahdapa token exchange → Hub API call
#
# This is the "Option C" flow: no static credentials anywhere.
set -euo pipefail

HUB_API="${HUB_API_URL:-https://hub.arbiter.demo}"
AHDAPA_URL="${AHDAPA_TOKEN_URL:-https://idm.arbiter.demo/idp/token}"
SPIRE_SOCKET="/tmp/spire-agent/public/api.sock"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  SPIFFE → IPA Federation: Zero-Credential Workload Auth  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 1. Show SPIRE agent health
echo "▸ Step 1: SPIRE Agent attestation status"
if spire-agent healthcheck -socketPath "$SPIRE_SOCKET" 2>/dev/null; then
    echo "  ✓ Agent attested to SPIRE Server"
else
    echo "  ✗ SPIRE Agent not running"
    exit 1
fi
echo ""

# 2. Fetch X.509 SVID
echo "▸ Step 2: Fetch X.509 SVID (mTLS identity)"
X509_OUT=$(spire-agent api fetch x509 -socketPath "$SPIRE_SOCKET" -output json 2>/dev/null)
SPIFFE_ID=$(echo "$X509_OUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
svids = data.get('svids', [data] if isinstance(data, dict) else data)
if svids:
    print(svids[0].get('spiffe_id', 'unknown'))
" 2>/dev/null)
echo "  SPIFFE ID: $SPIFFE_ID"
echo "  Certificate chain received (auto-rotated, ~1h TTL)"
echo ""

# 3. Fetch JWT SVID
echo "▸ Step 3: Fetch JWT SVID for arbiter-hub audience"
JWT_SVID=$(spire-agent api fetch jwt \
    -audience arbiter-hub \
    -socketPath "$SPIRE_SOCKET" \
    -output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
svids = data.get('svids', data if isinstance(data, list) else [data])
if svids:
    print(svids[0].get('svid', svids[0].get('token', '')))
" 2>/dev/null)

# Decode and display JWT claims
python3 -c "
import json, base64, sys
parts = '$JWT_SVID'.split('.')
header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))
payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
print(f\"  Algorithm: {header.get('alg')}\")
print(f\"  Subject:   {payload.get('sub')}\")
print(f\"  Audience:  {payload.get('aud')}\")
print(f\"  Expires:   {payload.get('exp')} (~5m TTL)\")
print(f\"  Issuer:    {payload.get('iss')}\")
" 2>/dev/null
echo ""

# 4. Token exchange via ahdapa
echo "▸ Step 4: RFC 8693 token exchange — JWT SVID → OAuth2 token"
echo "  POST $AHDAPA_URL"
echo "  grant_type=urn:ietf:params:oauth:grant-type:token-exchange"
echo "  subject_token=<jwt-svid>"
echo "  subject_token_type=urn:ietf:params:oauth:token-type:jwt"
echo ""

EXCHANGE_RESP=$(curl -sk -X POST "$AHDAPA_URL" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
    -d "subject_token=${JWT_SVID}" \
    -d "subject_token_type=urn:ietf:params:oauth:token-type:jwt" \
    -d "audience=arbiter-hub" \
    2>/dev/null)

ACCESS_TOKEN=$(echo "$EXCHANGE_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'access_token' in data:
    print(data['access_token'])
    token_type = data.get('token_type', 'bearer')
    expires = data.get('expires_in', '?')
    scope = data.get('scope', 'default')
    ipa_principal = data.get('ipa_principal', data.get('sub', '?'))
    print(f'  Token type:     {token_type}', file=sys.stderr)
    print(f'  Expires in:     {expires}s', file=sys.stderr)
    print(f'  IPA principal:  {ipa_principal}', file=sys.stderr)
    print(f'  Scope:          {scope}', file=sys.stderr)
elif 'error' in data:
    print(f\"  ✗ Exchange failed: {data['error']} — {data.get('error_description', '')}\", file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "  ✗ Token exchange not yet configured in ahdapa"
    echo "  (Federation policy needed — see hub-firstboot.sh step 9)"
    echo ""
    echo "  When configured, the chain is:"
    echo "    SPIRE Agent → JWT SVID → ahdapa exchange → OAuth2 token → Hub API"
    echo "    Zero static credentials. Identity rooted in SPIRE attestation,"
    echo "    bridged to IPA via ahdapa federation policy."
    exit 0
fi

echo "  ✓ OAuth2 access token received (IPA-backed identity)"
echo ""

# 5. Use the token to call Hub API
echo "▸ Step 5: Authenticated Hub API call"
echo "  GET ${HUB_API}/api/workloads"
echo "  Authorization: Bearer <oauth2-token>"
echo ""

API_RESP=$(curl -sk "${HUB_API}/api/workloads" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    2>/dev/null)

echo "  Response: $(echo "$API_RESP" | python3 -m json.tool 2>/dev/null | head -10)"
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Complete chain — no passwords, no API keys, no secrets:  ║"
echo "║                                                           ║"
echo "║  Process attested by SPIRE (unix selectors)               ║"
echo "║    → JWT SVID (5m, cryptographic proof of identity)       ║"
echo "║    → ahdapa token exchange (RFC 8693)                     ║"
echo "║    → OAuth2 access token (IPA service principal)          ║"
echo "║    → Hub API call (authorized via IPA identity)           ║"
echo "╚════════════════════════════════════════════════════════════╝"
