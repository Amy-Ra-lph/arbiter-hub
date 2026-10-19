# Arbiter Hub — Demo Walkthrough

**Lab:** Your deployment environment
**SERVER:** `<SERVER_FQDN>` (`<SERVER_IP>`, idm.arbiter.test)
**CLIENT:** `<CLIENT_FQDN>` (`<CLIENT_IP>`, runner.arbiter.test)

## Prerequisites

SSH access to both machines:
```bash
ssh root@<SERVER_FQDN>   # SERVER
ssh root@<CLIENT_FQDN>   # CLIENT
```

## Architecture Overview

```
┌─ SERVER (idm.arbiter.test) ─────────────────────┐
│  IPA Server (domain=arbiter.test)                │
│  ahdapa IdP (OIDC provider, :8090 → /idp proxy)  │
│  Keylime Verifier (:8881, mTLS)                  │
│  Keylime Registrar (:8890/:8891)                 │
└──────────────────────────────────────────────────┘
         │ OIDC tokens         │ mTLS attestation
         ▼                     ▼
┌─ CLIENT (runner.arbiter.test) ──────────────────┐
│  arbiter-hub-api (:8400, OIDC mode)              │
│  arbiter-hub-ui  (:8443 HTTPS, :8080 HTTP)       │
│  PostgreSQL (arbiter-db container)               │
│  Keylime Agent (swtpm TPM 2.0)                   │
└──────────────────────────────────────────────────┘
```

---

## 1. Verify Services Are Running

### SERVER — IPA + ahdapa + Keylime
```bash
ssh root@<SERVER_IP>

# IPA
ipactl status

# ahdapa IdP
systemctl status ahdapa
curl -sk https://idm.arbiter.test/idp/.well-known/openid-configuration | python3 -m json.tool

# Keylime
systemctl status keylime_verifier keylime_registrar
```

### CLIENT — Arbiter Hub + Keylime Agent
```bash
ssh root@<CLIENT_IP>

# Containers
podman ps --format "{{.Names}}\t{{.Status}}"
# Expect: arbiter-db, arbiter-hub-api, arbiter-hub-ui

# Keylime agent
systemctl status keylime_agent

# swtpm (software TPM)
systemctl status swtpm
```

---

## 2. OIDC Authentication Flow

### Get a token via client_credentials (machine-to-machine)
```bash
# On CLIENT — use your admin CLI client credentials
TOKEN=$(curl -sk -X POST https://idm.arbiter.test/idp/oauth2/token \
  -u "<CLIENT_ID>:<CLIENT_SECRET>" \
  -d "grant_type=client_credentials&scope=openid attestation-admin attestation-operator" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo $TOKEN
```

### Verify the token works against the API
```bash
curl -sk https://runner.arbiter.test:8443/api/health \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: https://runner.arbiter.test:8443" | python3 -m json.tool
```

Expected: health status with `"status": "ok"` and backend health info.

---

## 3. Attestation Flow — The Main Event

### 3a. Check existing workload
```bash
# List workloads
curl -sk https://runner.arbiter.test:8443/api/workloads/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: https://runner.arbiter.test:8443" | python3 -m json.tool
```

Note the workload ID and its metadata (keylime_agent_uuid).

### 3b. Trigger attestation
```bash
WORKLOAD_ID="<workload-uuid-from-step-3a>"

curl -sk -X POST "https://runner.arbiter.test:8443/api/workloads/${WORKLOAD_ID}/attest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: https://runner.arbiter.test:8443" \
  -H "Content-Type: application/json" | python3 -m json.tool
```

Expected output:
```json
{
    "verdict": "pass",
    "backend": "keylime",
    "evidence_hash": "<sha256>",
    "detail": {
        "operational_state": 3,
        "agent_id": "<keylime-agent-uuid>"
    }
}
```

**What's happening:** Arbiter Hub API → mTLS → Keylime Verifier → queries agent status → `operational_state: 3` ("Get Quote") = TPM attestation healthy → returns PASS verdict.

### 3c. Check workload state after attestation
```bash
curl -sk "https://runner.arbiter.test:8443/api/workloads/${WORKLOAD_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: https://runner.arbiter.test:8443" | python3 -m json.tool
```

State should be `healthy` (transitioned from `registered` after first PASS).

---

## 4. Register a New Workload (Optional)

```bash
curl -sk -X POST https://runner.arbiter.test:8443/api/workloads/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: https://runner.arbiter.test:8443" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Demo Workload",
    "ipa_principal": "demo-service/runner.arbiter.test@ARBITER.TEST",
    "workload_type": "service",
    "backend_type": "keylime",
    "metadata": {
        "keylime_agent_uuid": "<keylime-agent-uuid>",
        "keylime_agent_ip": "<CLIENT_IP>"
    }
  }' | python3 -m json.tool
```

Then attest it the same way as step 3b with the new workload ID.

---

## 5. Audit Trail

```bash
curl -sk "https://runner.arbiter.test:8443/api/audit/?limit=10" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: https://runner.arbiter.test:8443" | python3 -m json.tool
```

Every action (create, attest, state transition) recorded with actor identity from JWT.

---

## 6. Web UI (Browser)

### SSH tunnel for browser access
```bash
# From your workstation:
ssh -L 8443:<CLIENT_IP>:8443 -L 8080:<CLIENT_IP>:8080 root@<CLIENT_IP>
```

Then open: https://localhost:8443

Login with IPA credentials created during deployment.

The UI uses authorization code + PKCE flow through ahdapa → IPA authentication.

---

## 7. What Each Component Proves

| Component | What It Proves |
|-----------|---------------|
| **swtpm** | Software TPM 2.0 providing platform identity (EK, AK) |
| **Keylime Agent** | Continuously sends TPM quotes to verifier |
| **Keylime Verifier** | Validates TPM quotes, tracks operational_state |
| **Arbiter Hub API** | Queries verifier via mTLS, maps state to workload lifecycle |
| **ahdapa / IPA** | OIDC tokens for API auth, Kerberos realm for identity |
| **PostgreSQL** | Append-only audit log, workload state machine |
| **Web UI** | OIDC login (auth code + PKCE), dashboard visualization |

## Troubleshooting

**Token expired:** Re-run the TOKEN= command from step 2.

**403 Forbidden:** Scope mismatch — ensure token has `attestation-admin` scope.

**Keylime agent not healthy:** Check `systemctl status keylime_agent swtpm` on CLIENT. Agent needs swtpm running on ports 2321/2322.

**OIDC discovery fails:** Verify ahdapa is running on SERVER: `curl -sk https://idm.arbiter.test/idp/.well-known/openid-configuration`

**UI login redirect loop:** Clear browser cookies for localhost:8443. The OIDC state may be stale.
