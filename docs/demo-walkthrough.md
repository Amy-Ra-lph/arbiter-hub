# Arbiter Hub — Demo Walkthrough

**For:** lvrabec, Mubeen, demo attendees
**3-node topology:**
- **IDM:** `idm.arbiter.demo` — IPA + ahdapa + akamu + SPIRE + Keylime verifier
- **HUB:** `hub.arbiter.demo` — Arbiter Hub API/UI + enforcement-mcp + EDA
- **AGENT:** `agent.arbiter.demo` — OpenShell + linux-mcp-server + Falco + Keylime agent

## Prerequisites

SSH access to all three machines:
```bash
ssh root@<IDM>    # IPA server
ssh root@<HUB>    # Arbiter Hub
ssh root@<AGENT>  # Agent runtime
```

## Architecture

```
┌─ IDM (idm.arbiter.demo) ──────────────────────────┐
│  IPA Server (domain=arbiter.demo)                  │
│  ahdapa IdP (OIDC, ML-DSA-65 + ES256)             │
│  akamu MTC CA (ML-DSA-65, ACME)                    │
│  SPIRE Server (workload identity)                  │
│  Keylime Verifier (:8881) + Registrar (:8890)      │
│  Exfil Receiver (canary detection, :9443)          │
└─────────────────┬──────────────────────────────────┘
       OIDC tokens│  mTLS attestation
                  ▼
┌─ HUB (hub.arbiter.demo) ──────────────────────────┐
│  arbiter-hub-api (:8400, OIDC mode)                │
│  arbiter-hub-ui  (:8443 HTTPS)                     │
│  PostgreSQL (arbiter-db)                           │
│  enforcement-mcp (:8402)                           │
│  EDA controller (ansible-rulebook, :5001)          │
│  Webhook receiver (state_transition → EDA)         │
└─────────────────┬──────────────────────────────────┘
       webhooks   │  Falco alerts
                  ▼
┌─ AGENT (agent.arbiter.demo) ──────────────────────┐
│  OpenShell gateway (:8443) + supervisor            │
│  linux-mcp-server (19 RHEL tools)                  │
│  Keylime Agent (swtpm TPM 2.0)                     │
│  SPIRE Agent (JWT-SVID)                            │
│  Falco eBPF (→ Hub API /api/v1/falco/alerts)       │
│  Trust tier profiles (sovereign/verified/untrusted)│
│  Demo agents (governed + rogue)                    │
│  Falco→SIEM bridge (OCSF)                         │
└────────────────────────────────────────────────────┘
```

---

## Stage 1: Verify Services

### IDM node
```bash
ssh root@<IDM>

# IPA
ipactl status

# ahdapa IdP
systemctl status ahdapa
curl -sk https://idm.arbiter.demo/idp/.well-known/openid-configuration | python3 -m json.tool

# Keylime verifier + registrar
systemctl status keylime_verifier keylime_registrar

# SPIRE server
spire-server healthcheck -socketPath /tmp/spire-server/private/api.sock
```

### HUB node
```bash
ssh root@<HUB>

# Arbiter Hub containers
podman ps --format "{{.Names}}\t{{.Status}}"
# Expect: arbiter-hub-db, arbiter-hub-api, arbiter-hub-mcp

# API health
curl -s http://localhost:8400/healthz | python3 -m json.tool

# enforcement-mcp
systemctl status enforcement-mcp
curl -s http://localhost:8402/health | python3 -m json.tool

# EDA controller
systemctl status eda-arbiter
```

### AGENT node
```bash
ssh root@<AGENT>

# Keylime agent + swtpm
systemctl status keylime_agent swtpm

# Falco
systemctl status falco
falco --version

# OpenShell
systemctl status openshell-gateway

# SPIRE agent
spire-agent healthcheck -socketPath /tmp/spire-agent/public/api.sock

# Falco-SIEM bridge
systemctl status falco-siem-bridge
```

---

## Stage 2: OIDC Authentication

### Get a token (machine-to-machine)
```bash
# On HUB — use admin CLI client credentials
TOKEN=$(curl -sk -X POST https://idm.arbiter.demo/idp/oauth2/token \
  -u "<CLIENT_ID>:<CLIENT_SECRET>" \
  -d "grant_type=client_credentials&scope=openid attestation-admin" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token acquired: ${TOKEN:0:20}..."
```

### Verify against API
```bash
curl -s http://localhost:8400/healthz \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Stage 3: Single-Backend Attestation (Keylime TPM)

### 3a. Register a workload with Keylime backend
```bash
curl -s -X POST http://localhost:8400/api/v1/workloads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo-tpm-workload",
    "owner": "admin",
    "backends": ["keylime"],
    "metadata": {
        "keylime_agent_uuid": "<AGENT_UUID>",
        "keylime_agent_ip": "<AGENT_IP>"
    }
  }' | python3 -m json.tool
```

### 3b. Trigger attestation
```bash
curl -s -X POST http://localhost:8400/api/v1/workloads/demo-tpm-workload/attest \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: `"verdict": "pass"`, `"backend": "keylime"`, `operational_state: 3`.

**What happened:** API → mTLS → Keylime Verifier → TPM quote → PASS → state: `healthy`.

### 3c. Check workload state
```bash
curl -s http://localhost:8400/api/v1/workloads/demo-tpm-workload \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Stage 4: Multi-Backend Attestation

### 4a. Register workload with multiple backends
```bash
curl -s -X POST http://localhost:8400/api/v1/workloads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo-multi-workload",
    "owner": "admin",
    "backends": ["keylime", "cosign"],
    "metadata": {
        "keylime_agent_uuid": "<AGENT_UUID>",
        "keylime_agent_ip": "<AGENT_IP>",
        "cosign_image_ref": "quay.io/rhel-security/arbiter-hub-api:latest"
    }
  }' | python3 -m json.tool
```

### 4b. Attest — both backends run in parallel
```bash
curl -s -X POST http://localhost:8400/api/v1/workloads/demo-multi-workload/attest \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: composite verdict with per-backend results. FAIL on any backend = overall FAIL.

---

## Stage 5: Falco Runtime Monitoring → Attestation Failure

This is the "rogue agent" demo. Falco detects bad behavior → Arbiter Hub marks workload FAILED → EDA auto-quarantines.

### 5a. Check Falco rules loaded
```bash
# On AGENT
cat /etc/falco/rules.d/arbiter-rules.yaml
```

### 5b. Start the good workload
```bash
# On AGENT
podman start demo-good-workload
```

### 5c. Simulate an attack (triggers Falco)
```bash
# On AGENT — exec into good workload, try to read /etc/shadow
podman exec demo-good-workload cat /etc/shadow
```

### 5d. Watch Falco alert arrive at Hub
```bash
# On HUB — check API logs
podman logs arbiter-hub-api --tail 20 | grep -i falco
```

### 5e. Workload state should be FAILED
```bash
# On HUB
curl -s http://localhost:8400/api/v1/workloads/demo-good-workload \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

State: `failed`. The Falco alert triggered a state transition.

---

## Stage 6: EDA Auto-Remediation

### 6a. Check webhook registration
```bash
curl -s http://localhost:8400/api/v1/webhooks \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### 6b. The webhook fired on state transition (HEALTHY→FAILED)
```bash
# On HUB — check EDA logs
journalctl -u eda-arbiter --no-pager --since "5 minutes ago" | tail -20
```

EDA received the `state_transition` event and ran `quarantine.yml`:
- Disconnected the container from network
- Notified Arbiter Hub via remediation API

### 6c. Verify container quarantined
```bash
# On AGENT
podman inspect demo-good-workload --format '{{.HostConfig.NetworkMode}}'
# Expected: none (disconnected)
```

---

## Stage 7: Rogue Agent Demo (Trust Tiers)

### 7a. Run governed agent (well-behaved)
```bash
# On AGENT
python3 /opt/demo/agents/governed_agent.py --profile verified
```

Governed agent respects sandbox boundaries, uses OAuth2 tokens, no Falco alerts.

### 7b. Run rogue agent (triggers everything)
```bash
# On AGENT
python3 /opt/demo/agents/rogue_agent.py
```

Rogue agent attempts:
- Read `/etc/shadow` → Falco alert → workload FAILED
- Read honeypot AWS creds → Falco alert
- Exfiltrate data to exfil receiver → detected
- Reverse shell attempt → Falco CRITICAL → forensic collection

### 7c. Watch the cascade
```bash
# On HUB — real-time EDA events
journalctl -u eda-arbiter -f

# On IDM — exfil receiver catches the attempt
journalctl -u exfil-receiver --since "2 minutes ago"
```

---

## Stage 8: KBS Secrets (Key Broker)

### 8a. Store a secret
```bash
curl -s -X POST http://localhost:8400/kbs/v0/resource/default/demo/my-secret \
  -H "Authorization: Bearer $TOKEN" \
  -d "secret-value-for-attested-workloads" | python3 -m json.tool
```

### 8b. Retrieve (only attested workloads should access)
```bash
curl -s http://localhost:8400/kbs/v0/resource/default/demo/my-secret \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Stage 9: Audit Trail

```bash
curl -s "http://localhost:8400/api/v1/audit?limit=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Every action recorded: create, attest, state transition, remediation, webhook delivery. Actor identity from JWT. Append-only PostgreSQL triggers prevent deletion.

---

## Stage 10: Web UI

### SSH tunnel for browser access
```bash
ssh -L 8443:<HUB_IP>:8443 root@<HUB>
```

Open: https://localhost:8443

Login with IPA credentials. The UI shows:
- Dashboard with workload health overview
- Per-workload attestation history and state machine
- Backend status (Keylime, cosign, etc.)
- Audit log viewer
- Policy management

---

## What Each Component Proves

| Component | What It Proves |
|-----------|---------------|
| **swtpm + Keylime Agent** | Hardware-rooted identity via TPM 2.0 quotes |
| **Keylime Verifier** | Continuous TPM attestation, IMA file integrity |
| **Arbiter Hub API** | Multi-backend attestation orchestration, 7-state machine |
| **ahdapa + IPA** | OIDC/OAuth2 for API auth, PQC-ready (ML-DSA-65) |
| **akamu** | PQC certificate authority (ML-DSA-65 MTC certs) |
| **SPIRE** | Workload identity (JWT-SVID) federated with ahdapa |
| **Falco eBPF** | Runtime behavioral monitoring → attestation failure |
| **EDA** | Event-driven auto-remediation (quarantine, re-attest, forensics) |
| **Webhooks** | Real-time state transition notifications (HMAC-signed) |
| **enforcement-mcp** | SELinux/fapolicyd policy enforcement via MCP |
| **OpenShell** | Sandboxed agent runtime with GSSAPI auth |
| **Trust Tiers** | Graduated sandbox policies (sovereign/verified/untrusted) |
| **Mock KBS** | Trustee-compatible key broker for secret-gating |
| **OCSF Bridge** | Security events normalized for SIEM consumption |
| **Exfil Receiver** | Canary detection for data exfiltration attempts |

## Troubleshooting

**Token expired:** Re-run the TOKEN= command from Stage 2.

**403 Forbidden:** Scope mismatch — ensure token has `attestation-admin` scope.

**Keylime agent not healthy:** Check `systemctl status keylime_agent swtpm` on AGENT.

**Falco not alerting:** Verify rules loaded: `falco --list | grep arbiter`. Check eBPF probe: `falco --version` should show `ebpf`.

**EDA not triggering:** Check webhook registration (Stage 6a) and EDA service: `systemctl status eda-arbiter`.

**OIDC discovery fails:** Verify ahdapa on IDM: `curl -sk https://idm.arbiter.demo/idp/.well-known/openid-configuration`

**UI login redirect loop:** Clear browser cookies for localhost:8443.
