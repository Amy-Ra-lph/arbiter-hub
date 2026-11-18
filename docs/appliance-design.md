# Arbiter Hub Appliance — Design Document

**Date:** 2026-11-11
**Author:** Amy Ralph, Principal PM — RHEL Security / IdM
**Status:** Draft
**Scope:** Packaging Arbiter Hub as a bootc-based appliance for easy deployment

---

## 1. Problem Statement

Arbiter Hub currently requires ~20 Ansible playbooks, manual registry logins, per-component certificate distribution, and deep familiarity with keylime/cosign/Falco configuration. A customer or field engineer deploying this on a single lab, edge site, or customer demo should not need to understand the internal wiring. The deployment experience should be: boot the appliance image, point it at IdM, wait, done.

---

## 2. Appliance Model

Three-image architecture. IdM is an external dependency, not an embedded component. Arbiter ships two images: server and agent.

### 2.1 Deployment Topology

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Customer Environment                         │
│                                                                      │
│  ┌─────────────────────┐     ┌─────────────────────────────────┐    │
│  │  IdM Primary         │     │  Arbiter Server (bootc)         │    │
│  │  (existing or new)   │     │                                 │    │
│  │                      │◄────│  IPA client enrollment          │    │
│  │  FreeIPA server      │     │  keylime-verifier + registrar   │    │
│  │  ahdapa (OIDC)       │     │  Hub API + PostgreSQL + KBS     │    │
│  │  akamu (ACME)        │     │  enforcement-mcp                │    │
│  │  IPA CA              │     │  EDA + webhook listener         │    │
│  │                      │     │  nginx (UI + reverse proxy)     │    │
│  │  Port: 443, 389,     │     │  cosign                         │    │
│  │        88, 464       │     │                                 │    │
│  └──────────┬───────────┘     │  Port: 8400 (API), 8080 (UI),  │    │
│             │                 │        8891 (registrar)          │    │
│             │                 └──────────────┬──────────────────┘    │
│             │                                │                       │
│             │         ┌──────────────────────┤                       │
│             │         │                      │                       │
│  ┌──────────▼─────────▼──┐    ┌──────────────▼──────────────────┐   │
│  │  Arbiter Agent 1       │    │  Arbiter Agent N                │   │
│  │  (bootc)               │    │  (bootc)                        │   │
│  │                        │    │                                  │   │
│  │  IPA client            │    │  IPA client                     │   │
│  │  keylime-agent-rust    │    │  keylime-agent-rust             │   │
│  │  swtpm / hardware TPM  │    │  swtpm / hardware TPM          │   │
│  │  Falco (eBPF)          │    │  Falco (eBPF)                   │   │
│  │  OpenShell (3 tiers)   │    │  OpenShell (3 tiers)            │   │
│  │  linux-mcp-server      │    │  linux-mcp-server               │   │
│  └────────────────────────┘    └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Platform Targets

| Base OS | bootc Image | Status |
|---------|-------------|--------|
| Fedora (latest) | `quay.io/fedora/fedora-bootc:44` | PoC — active development |
| RHEL 10 | `registry.redhat.io/rhel10/rhel-bootc:10.0` | Production target |

Both Arbiter Server and Agent images build from the same base. CI tests against both. Package availability is equivalent — keylime, cosign, Falco, freeipa-client all ship in Fedora and RHEL 10.

### 2.3 Single IdM Domain Model

Arbiter Server and all Agents enroll as clients of one IPA domain. IPA's existing trust and authorization rules govern all access:

- **HBAC (Host-Based Access Control)**: Controls which users can access which Arbiter nodes. An `arbiter-servers` HBAC rule can restrict SSH/console access to the server node. An `arbiter-agents` rule can restrict agent access to workload operators.
- **Sudo rules**: IPA sudo rules control privilege escalation on Arbiter nodes, same as any other IPA-enrolled host.
- **Role-Based Access Control**: Arbiter-specific roles (`attestation-admin`, `attestation-reader`, `policy-editor`) are IPA roles. Permission grants flow through IPA delegation — no separate RBAC system.
- **Service delegation**: Hub API's HTTP service principal uses constrained delegation for S4U2Proxy when forwarding user identity to backends.
- **Trust agreements**: If the IPA domain has Active Directory trust configured, AD users can authenticate to the Hub UI via SPNEGO and receive Arbiter RBAC roles mapped from AD groups.

No multi-domain support. One Arbiter Server → one IPA domain. If a customer has multiple IPA domains, each gets its own Arbiter Server. This keeps the trust model simple and auditable.

### 2.4 Why IdM Is Separate

1. **Customer may already have IdM.** Most RHEL environments with identity management already run IPA. Requiring a new IPA instance for Arbiter is a non-starter.
2. **Separation of concerns.** IdM is an identity provider. Arbiter is an attestation platform that consumes identity. Embedding IPA inside Arbiter creates a monolith with two upgrade lifecycles, two backup strategies, and two failure domains tangled together.
3. **Flexible deployment.** Arbiter Server can join any IPA domain — same one running the customer's existing hosts, users, and services. No identity silo.
4. **IdM Image Mode already exists.** The bootc image for IdM is production-tested (`quay.io/rhel-security/arbiter-bootc:idm-identity`). Shipping it separately means each image evolves independently.

### 2.5 Image Summary

| Image | Role | What It Contains | What It Needs |
|-------|------|-----------------|---------------|
| **IdM Primary** | Identity provider | FreeIPA + ahdapa + akamu + IPA CA | DNS, network | 
| **Arbiter Server** | Attestation control plane | Hub API, PostgreSQL, KBS, keylime-verifier, keylime-registrar, enforcement-mcp, EDA, nginx, cosign | Existing IdM to enroll against |
| **Arbiter Agent** | Attested execution node | keylime-agent, swtpm, Falco, OpenShell, linux-mcp-server | Existing IdM + Arbiter Server |

Quay tags:
- `quay.io/rhel-security/arbiter-bootc:idm-identity` (existing)
- `quay.io/rhel-security/arbiter-bootc:arbiter-server` (new)
- `quay.io/rhel-security/arbiter-bootc:arbiter-agent` (existing)

---

## 3. Configuration UX

### 3.1 Arbiter Server — First Boot

Config file at `/etc/arbiter/server.env`:

```ini
# ── Required (3 values) ─────────────────────────────────────────────
ARBITER_IPA_SERVER=idm.example.com       # existing IdM server FQDN
ARBITER_IPA_DOMAIN=example.com           # IPA domain
ARBITER_IPA_ADMIN_PASSWORD=<password>    # IPA admin (for enrollment + OIDC client registration)

# ── Optional (sane defaults) ────────────────────────────────────────
ARBITER_HOSTNAME=arbiter.example.com     # defaults to $(hostname -f)
ARBITER_KEYLIME_ENABLED=true             # verifier + registrar
ARBITER_COSIGN_ENABLED=true              # image signature verification
ARBITER_FALCO_ENABLED=true               # eBPF runtime monitoring on agents
ARBITER_EDA_ENABLED=true                 # Event-Driven Ansible remediation
ARBITER_AUTH_MODE=oidc                   # oidc | spnego | dev

# ── Advanced (override only) ───────────────────────────────────────
ARBITER_DB_PASSWORD=<auto-generated>
ARBITER_WEBHOOK_SECRET=<auto-generated>
ARBITER_OIDC_CLIENT_ID=arbiter-hub       # registered on IdM's ahdapa
ARBITER_OIDC_CLIENT_SECRET=<auto-generated>
ARBITER_KEYLIME_VERIFIER_IP=0.0.0.0      # bind address
ARBITER_KEYLIME_REGISTRAR_PORT=8891
```

Three required values — all related to the existing IdM server. No realm, no DS password (those belong to IdM). Auto-generated secrets use `openssl rand -base64 32`, stored in podman secrets.

### 3.2 First Boot Sequence (Arbiter Server)

```
Phase 1: Identity Enrollment
  1. ipa-client-install --server=IPA_SERVER --domain=IPA_DOMAIN -p admin -w <password> -U
  2. kinit admin → register OIDC client with ahdapa on IdM
  3. Request HTTP service principal for SPNEGO (HTTP/arbiter.example.com)
  4. Fetch IPA CA cert → /etc/ipa/ca.crt (happens automatically with client enrollment)
  ↓
Phase 2: Attestation Infrastructure
  5. keylime-verifier start (TLS auto-generate, bind 0.0.0.0)
  6. keylime-registrar start
  7. cosign key-pair generate → /etc/arbiter/cosign/
  ↓
Phase 3: Hub Services (Quadlets)
  8. PostgreSQL init + Alembic migration
  9. Hub API start — backends auto-register based on available services:
     - keylime: if verifier URL is reachable
     - cosign: if public key exists
     - falco: detected when agents report in
  10. KBS start
  11. enforcement-mcp start
  12. EDA + webhook listener start
  13. nginx start (UI + reverse proxy to API :8400)
  ↓
Phase 4: Seed + Finalize
  14. Default trust policies seeded (sovereign, verified, untrusted)
  15. RBAC roles created in IPA (attestation-admin, attestation-reader, policy-editor)
  16. Enrollment tokens generated → /etc/arbiter/enrollment-tokens/
  17. IPA admin password redacted from config file
  18. Stamp file → /var/lib/arbiter/.firstboot-complete
```

Total time: ~5-8 minutes (faster than old controller — no IPA server install). User gets:
- Hub dashboard at `https://arbiter.example.com:8080/`
- API at `https://arbiter.example.com:8400/docs`
- OIDC login via IdM's ahdapa (SSO with IPA WebUI)

### 3.3 Agent — First Boot

Three values at `/etc/arbiter/agent.env`:

```ini
ARBITER_SERVER=arbiter.example.com       # Arbiter Server FQDN
ARBITER_IPA_SERVER=idm.example.com       # IdM server FQDN
ARBITER_ENROLLMENT_TOKEN=<one-time token from Arbiter Server>
```

Optional:
```ini
ARBITER_TRUST_TIER=verified              # sovereign | verified | untrusted (default: verified)
```

Sequence:
1. IPA client enroll against IdM server (using enrollment token — no admin password)
2. Detect TPM: `/dev/tpmrm0` → hardware TPM; absent → start swtpm
3. keylime-agent start → registers with Arbiter Server's verifier (port 8891)
4. Falco start with tier-appropriate rules
5. OpenShell sandboxes created at specified trust tier
6. linux-mcp-server start
7. Self-register with Hub API as attested workload (Kerberos auth via SPNEGO)
8. First attestation triggers automatically

Total time: ~3 minutes. Agent appears in Hub dashboard.

### 3.4 Enrollment Flow

```
                   IdM Primary                 Arbiter Server              Agent Node
                   ──────────                  ──────────────              ──────────
                        │                            │                         │
                        │     ipa-client-install      │                         │
                        │◄───────────────────────────│                         │
                        │     (admin password)        │                         │
                        │                            │                         │
                        │     register OIDC client    │                         │
                        │◄───────────────────────────│                         │
                        │                            │                         │
                        │                            │  generate enrollment     │
                        │                            │  tokens (batch of N)     │
                        │                            │                         │
                        │                            │     admin copies token   │
                        │                            │─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─►│
                        │                            │                         │
                        │     ipa-client-install      │                         │
                        │◄─────────────────────────────────────────────────────│
                        │     (enrollment token)      │                         │
                        │                            │                         │
                        │                            │  keylime-agent register  │
                        │                            │◄────────────────────────│
                        │                            │                         │
                        │                            │  Hub API self-register   │
                        │                            │◄────────────────────────│
                        │                            │  (SPNEGO auth)           │
```

Admin password only used once: Arbiter Server → IdM enrollment. Never on agents. Agents use single-use enrollment tokens generated by Arbiter Server and passed through IPA's OTP mechanism.

### 3.5 Trust Tier Profiles

One knob replaces per-component tuning:

| Tier | OpenShell | Falco | Keylime | Network | Use Case |
|------|-----------|-------|---------|---------|----------|
| `sovereign` | Full host access | Audit-only (log, no block) | TPM attestation, 1h TTL | Unrestricted | Trusted internal workloads |
| `verified` | gVisor sandbox | Active enforcement (kill on violation) | TPM + IMA, 15min TTL | Egress filtered | Standard production |
| `untrusted` | Read-only rootfs, no /dev | Strict + process whitelist | TPM + IMA + measured boot, 5min TTL | No egress | External / third-party code |

Profile definitions ship as YAML in `/etc/arbiter/trust-profiles/`. Customizable post-deploy.

---

## 4. Security Assessment

### 4.1 STRIDE Analysis — Appliance-Specific Threats

Building on the existing threat model (`docs/security-threat-model.md`), these are new or changed threats introduced by the appliance packaging. The three-node separation introduces a network trust boundary between IdM and Arbiter that the two-node model did not have.

#### Spoofing

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **S-A1: Enrollment token replay** — stolen token used to enroll rogue agent | Token is single-use, deleted from Arbiter Server after first enrollment. 24h expiry. | LOW — if token leaks before use, attacker has a window. Mitigated by short expiry + IPA audit log of enrollments. |
| **S-A2: Agent impersonates Arbiter Server** — rogue node claims to be the verifier | Agent resolves Arbiter Server via IPA DNS. Keylime agent validates verifier TLS cert chain. Arbiter Server has IPA service principal (HTTP/arbiter.example.com) — agents verify via Kerberos. | LOW — requires compromising IPA CA or DNS. |
| **S-A3: Rogue Arbiter Server enrolls against IdM** — attacker stands up fake Arbiter Server | Enrollment requires IPA admin password. Post-enrollment, Arbiter Server holds only its own Kerberos keytab (not admin credentials). IPA audit log shows enrollment. | LOW — requires admin password. Mitigated by redacting password immediately after enrollment. |
| **S-A4: Config file credential theft during firstboot** — IPA admin password readable before redaction | Config file created with `chmod 600`. Redaction runs immediately after IPA client enrollment completes (Phase 1, step 4). | MEDIUM — ~2-3 minute window where admin password in file. Shorter than old model (no IPA server install delay). |

#### Tampering

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **T-A1: Appliance image modified pre-deployment** — attacker alters qcow2/ISO before boot | Images signed with cosign. bootc `ostree` validates image layers at boot via dm-verity. | LOW — requires intercepting distribution channel. |
| **T-A2: Agent bootc image layers swapped** — malicious image passes attestation | cosign backend verifies image signature against Arbiter Server's public key before workload registration. Measured boot backend validates PCR values. | LOW — both backends must be fooled simultaneously. |
| **T-A3: Firstboot script modified on disk** | Script in `/usr` (read-only ostree partition). Cannot be modified at runtime. | NEGLIGIBLE |
| **T-A4: Man-in-the-middle between Arbiter Server and IdM** — attacker intercepts enrollment traffic | IPA client enrollment uses LDAPS/Kerberos (encrypted). OIDC client registration uses HTTPS to ahdapa. IPA CA cert pinned during enrollment. | LOW — standard TLS protections apply. |

#### Repudiation

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **R-A1: Enrollment not auditable** | IPA logs client enrollment. Hub API records workload registration with timestamp + Kerberos principal. PostgreSQL triggers prevent audit log deletion. | LOW |
| **R-A2: Trust tier change untracked** | Tier changes flow through Hub API `PATCH /workloads/{id}` — records state transitions with actor identity. | LOW |

#### Information Disclosure

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **I-A1: Auto-generated secrets predictable** | `openssl rand -base64 32` (reads from `/dev/urandom`). | NEGLIGIBLE |
| **I-A2: Enrollment token exfiltrated via console log** | Token written to file only (`/etc/arbiter/enrollment-tokens/`), not stdout. File mode 0600. | LOW |
| **I-A3: Keylime mTLS certs accessible from Hub containers** | Mount is `:ro`. Container runs as UID 1001. Certs are mode 0600 root-owned. Conditional on backend enablement (Jinja2 template). | MEDIUM — needs review. |
| **I-A4: IPA admin password transits network to IdM** | Standard IPA enrollment path — Kerberos kinit over encrypted channel. Password not stored after enrollment. | LOW |
| **I-A5: Arbiter Server holds IPA keytab** — compromise exposes identity domain | Keytab is for service principal only (HTTP/arbiter.example.com), not admin. Attacker gains ability to impersonate the Arbiter Server service, not IPA admin. IPA can revoke the keytab remotely. | LOW |

#### Denial of Service

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **D-A1: Agent flood — mass enrollment exhausts Arbiter Server** | Rate limiting (slowapi). Single-use tokens. IPA throttles client enrollments. | MEDIUM — determined attacker with many tokens. Future: enrollment quotas. |
| **D-A2: Firstboot hangs** | Per-phase timeouts. Stamp file on success only. `systemctl restart arbiter-firstboot` is idempotent. | LOW |
| **D-A3: IdM unavailable — Arbiter Server cannot start** | Firstboot retries IPA enrollment (3 attempts, exponential backoff). If IdM is down, firstboot fails cleanly with actionable error. Arbiter does not start half-configured. | LOW — but Arbiter Server is non-functional until IdM is reachable. Document as prerequisite. |

#### Elevation of Privilege

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **E-A1: Agent-to-server lateral movement** | Agent holds IPA client keytab only. keylime-agent connects to registrar (8891) only. Hub API requires OIDC/SPNEGO auth. No SSH from agent to server. | LOW |
| **E-A2: Hub container escape to host** | Quadlet containers run rootless (UID 1001). No `--privileged`. Volumes `:ro` except DB data. `SecurityLabelDisable=true` needs replacement with custom SELinux policy. | MEDIUM |
| **E-A3: Trust tier escalation** | Tier set at enrollment by Arbiter Server. Agent cannot modify own tier. Changes require attestation-admin role via Hub API. | LOW |
| **E-A4: Arbiter Server escalates to IPA admin** | Server holds service keytab, not admin credentials. Admin password redacted from config after enrollment. No cached admin TGT. | LOW |

### 4.2 Security Hardening Checklist

- [ ] Enrollment tokens: single-use + 24h TTL + batch generation cap
- [ ] Container SELinux: replace `SecurityLabelDisable=true` with custom policy module
- [ ] Firstboot config: move from env file to podman secrets pre-firstboot
- [ ] Hub API: disable `auth_mode=dev` in appliance builds (hardcode to `oidc` or `spnego`)
- [ ] Inter-container mTLS: currently plaintext on internal podman bridge network
- [ ] Cosign image verification of server image at boot (dm-verity + cosign)
- [ ] Keylime cert volume mount: conditional on backend enablement (already in Jinja2 template)
- [ ] Rate limit enrollment API separately from general API endpoints
- [ ] IPA admin password: redact within 30s of successful enrollment, not at end of firstboot
- [ ] Arbiter Server keytab: restrict to HTTP service principal only, verify no admin delegation

### 4.3 Trust Boundary Diagram

```
┌──── Trust Boundary 1: Identity ──────────────────────────────────┐
│  IdM Primary                                                      │
│  - IPA CA (root of trust for all TLS + Kerberos)                 │
│  - ahdapa (OIDC token issuer)                                     │
│  - User/host/service database                                     │
│                                                                    │
│  Compromise here = full domain compromise                         │
└───────────────────────────────────────────────────────────────────┘
          │ Kerberos, LDAPS, HTTPS (OIDC)
          ▼
┌──── Trust Boundary 2: Attestation Control Plane ─────────────────┐
│  Arbiter Server                                                    │
│  - Hub API (attestation decisions)                                │
│  - keylime-verifier (TPM quote validation)                        │
│  - PostgreSQL (attestation records, audit log)                    │
│  - cosign (image signature verification)                          │
│                                                                    │
│  Compromise here = false attestation verdicts, secret release     │
│  Does NOT compromise identity domain (no admin creds)             │
└───────────────────────────────────────────────────────────────────┘
          │ keylime mTLS (8891), Hub API HTTPS (8400)
          ▼
┌──── Trust Boundary 3: Workload Execution ────────────────────────┐
│  Arbiter Agent (N nodes)                                          │
│  - Untrusted workloads in OpenShell sandboxes                     │
│  - Runtime monitoring (Falco)                                     │
│  - TPM-backed attestation evidence (keylime-agent)                │
│                                                                    │
│  Compromise here = single workload node, contained by sandbox     │
│  Does NOT propagate to other agents or server (no lateral creds)  │
└───────────────────────────────────────────────────────────────────┘
```

This three-boundary model is stronger than the original two-boundary model. Compromising the Arbiter Server does not give access to the identity domain. Compromising an agent does not give access to the attestation control plane.

---

## 5. UX Assessment

### 5.1 Personas

| Persona | Goal | Current Pain | Appliance Improvement |
|---------|------|-------------|----------------------|
| **Field SE** | Demo attestation to customer in 30 min | 20 playbooks, 3+ VMs, registry logins, cert wiring | Boot server + agent images, point at existing IdM, paste 6 config values, wait 11 min |
| **Security Architect** | Evaluate attestation for SOC integration | Must understand keylime, cosign, Falco internals | Trust tiers abstract backend complexity; API + OCSF events integrate with existing SIEM |
| **Platform Admin** | Add attestation to existing IdM deployment | New tool with unfamiliar deployment model | Arbiter joins existing IPA domain — same CA, same users, same admin tools. No identity silo. |
| **Developer** | Test workload in attested sandbox | No local option; depends on PoC lab | Agent image runs on any podman/KVM host |

### 5.2 UX Principles

1. **Three required values for server, three for agent.** Server needs: IPA server FQDN, IPA domain, IPA admin password. Agent needs: Arbiter Server FQDN, IPA server FQDN, enrollment token. Everything else defaults.

2. **Bring your own IdM.** Arbiter does not force a new identity silo. Customer points Arbiter at their existing IPA domain. Users, groups, RBAC, and CA are shared. SSO works out of the box.

3. **Enrollment tokens, not passwords.** Arbiter Server generates tokens. Agents consume tokens. IPA admin password only used once (server enrollment) and immediately redacted.

4. **Trust tier as one knob.** `sovereign | verified | untrusted` — each is a pre-validated policy bundle covering Falco rules, OpenShell limits, keylime intervals, and network policy.

5. **Backend auto-detection.** Backends self-register based on available services. No manual "enable keylime" step — if the verifier is running, the backend registers.

6. **Progressive disclosure.** First boot shows phase progress. Dashboard shows traffic-light status. API docs at `/docs` for power users. Full audit log for compliance teams.

### 5.3 UX Gaps and Risks

| Gap | Severity | Mitigation |
|-----|----------|-----------|
| **No TUI/wizard for first boot** — user must create config file manually | MEDIUM | Phase 1: config file. Phase 2: `arbiter-setup` TUI (dialog-based, like `nmtui`). |
| **No web-based setup wizard** | LOW | Lower priority than TUI. Hub dashboard could include first-run wizard, but adds frontend complexity. |
| **Agent enrollment requires copying token manually** | MEDIUM | Phase 1: copy-paste. Phase 2: QR code on server console. Phase 3: IPA OTP-based enrollment (no separate token). |
| **Requires existing IdM** | MEDIUM | Most target customers already have IPA. For greenfield: document IdM Image Mode as prerequisite, or provide a `quickstart.sh` that boots both. |
| **Appliance updates** — how does user update bootc image? | HIGH | `bootc upgrade` pulls new image layer. Rollback via `bootc rollback`. DB migrations must be forward-compatible. Document upgrade path. |
| **Multi-server HA** | MEDIUM | Arbiter-native replication (§8) — `arbiter-repl` daemon syncs config state between up to 3 servers. Keylime verifier active-passive with automatic failover. |
| **Offline / air-gapped deployment** | HIGH | Images must be self-contained. No runtime container pulls. cosign verification with bundled public keys (no Rekor). Document air-gap deployment. |
| **IdM down at Arbiter boot time** | LOW | Firstboot retries with backoff. Clear error message. Documented prerequisite. |

### 5.4 Day-2 Operations

| Operation | Method |
|-----------|--------|
| Add agent | Boot agent image, paste enrollment token |
| Remove agent | Hub dashboard → Workloads → Revoke, or `curl -X POST /workloads/{id}/revoke` |
| Rotate secrets | `arbiter-rotate-secrets` (rotates DB password, webhook secret, cosign keys) |
| Upgrade | `bootc upgrade` on server and agents (rolling — agents first, then server) |
| Backup | PostgreSQL `pg_dump` + cosign keys + trust profiles (scripted as `arbiter-backup`). IPA backup managed separately by IdM admin. |
| Monitor | Prometheus `/metrics`, OCSF events via webhook to SIEM |
| Add backends | Install keylime on new infra → Hub API auto-detects on next health check |

---

## 6. UI Integration — IdM, Satellite, and Insights

### 6.1 Strategic Context

Arbiter Hub ships with its own dashboard (PatternFly 6, React SPA). Long-term, attestation status should surface in the management tools operators already use daily. The standalone dashboard remains the deep-dive tool; IdM/Satellite/Insights provide contextual views.

### 6.2 Integration Architecture

```
                    ┌─────────────────────────────────────┐
                    │         Arbiter Hub API :8400        │
                    │    (single source of truth for       │
                    │     workload trust state)            │
                    └──────┬──────────┬──────────┬────────┘
                           │          │          │
           ┌───────────────▼┐   ┌─────▼──────┐  ┌▼──────────────┐
           │  IdM WebUI      │   │ Satellite  │  │ Insights      │
           │  Plugin/Tab     │   │ Module     │  │ Integration   │
           │                 │   │            │  │               │
           │ "Attestation"   │   │ Compliance │  │ Risk/Trust    │
           │ tab on host     │   │ report     │  │ dashboard     │
           │ detail page     │   │ column     │  │ fleet-wide    │
           └─────────────────┘   └────────────┘  └───────────────┘
```

All three integrations read from the same Hub API. No data duplication, no sync jobs.

### 6.3 IdM WebUI Integration (Nearest-Term)

IPA WebUI and Arbiter Hub UI are both PatternFly applications. Natural fit.

1. **IPA plugin tab**: "Attestation" tab on the host detail page. REST calls to Hub API (`/workloads?host={fqdn}`). Shows: current trust state, last attestation time, active backends, trust tier, link to full Hub dashboard.
2. **IPA-managed objects**: Arbiter workloads map 1:1 to IPA hosts. Agent enrollment creates the IPA host entry. No new object type in IPA schema.
3. **IPA RBAC**: Arbiter roles (`attestation-admin`, `attestation-reader`, `policy-editor`) created as IPA roles during Arbiter Server firstboot. Permission delegation via IPA's existing model.
4. **Single sign-on**: Hub UI authenticates via OIDC (ahdapa on IdM) or SPNEGO (Kerberos). Same credential as IPA WebUI. One `kinit` or one browser login — no second auth prompt.
5. **Reverse integration**: Arbiter Hub dashboard links back to IPA WebUI for host details, user management, certificate operations. Each tool stays in its lane.

### 6.4 Satellite Integration (Mid-Term)

Satellite manages host lifecycle. Attestation is a compliance signal in that lifecycle.

1. **Foreman plugin** (`foreman_arbiter`): Attestation status column in host list. Color-coded (green/yellow/red) matching state machine (HEALTHY/STALE/FAILED). Design reference: `project_foreman-arbiter-plugin-2026-10-23.md`.
2. **Content view policy**: Gate content delivery on attestation state. Host in FAILED state → block package updates until remediated. Hub API webhook → Satellite host status update.
3. **Provisioning hook**: Satellite provisions a new host → auto-enroll as Arbiter Agent. Activation key includes enrollment token. Zero-touch agent deployment.
4. **Compliance report**: Attestation results as compliance report type. Maps findings to OpenSCAP-compatible format for unified compliance dashboard.

### 6.5 Insights Integration (Longer-Term)

Fleet-wide visibility via console.redhat.com.

1. **Host inventory enrichment**: Attestation state as system fact. Appears alongside subscription status, compliance score, vulnerability count.
2. **Advisor rules**: "Host has failed attestation for >24h" as recommendation. Severity based on trust tier (untrusted failure = critical, sovereign failure = info).
3. **Risk dashboard**: Aggregate attestation health across fleet. "87% HEALTHY, 8% STALE, 5% FAILED." Filterable by trust tier, backend type, IPA domain.
4. **Remediation playbooks**: Insights remediations trigger Arbiter re-attestation via EDA. Detection (Insights) → action (Arbiter EDA + Ansible).
5. **Data flow**: Hub API → OCSF events → Insights ingestion API. OCSF already implemented in Hub telemetry module.

### 6.6 UI Strategy Summary

| Phase | Surface | What Users See | Effort |
|-------|---------|---------------|--------|
| **Now** | Standalone Hub dashboard | Full attestation management | Done |
| **v1.1** | IdM WebUI plugin tab | Attestation status on host detail page; SSO login | Small (2-3 weeks) |
| **v2** | Satellite foreman_arbiter | Attestation column in host list; compliance report; provisioning hook | Medium (6-8 weeks) |
| **v3** | Insights | Fleet-wide risk dashboard; Advisor rules; remediation playbooks | Large (cross-team) |

The standalone dashboard is always available. IdM/Satellite/Insights are contextual views into the same API.

---

## 7. Image Build and Distribution

### 7.1 Repository Structure

```
arbiter-hub/
  containerfiles/
    Containerfile.server          # keylime-verifier + Hub Quadlets + enforcement-mcp
    Containerfile.agent           # keylime-agent + swtpm + Falco + OpenShell
  config/
    arbiter-firstboot.sh          # reads ARBITER_ROLE from image label
    arbiter-firstboot.service     # systemd oneshot, ConditionPathExists guard
    trust-profiles/
      sovereign.yaml
      verified.yaml
      untrusted.yaml
    seed-policies.json
```

IdM Containerfile remains in `idm-image-mode/` — separate repo, separate lifecycle.

### 7.2 Arbiter Server Containerfile Sketch

```dockerfile
# Fedora (PoC):  FROM quay.io/fedora/fedora-bootc:44
# RHEL 10 (prod): FROM registry.redhat.io/rhel10/rhel-bootc:10.0
ARG BASE_IMAGE=quay.io/fedora/fedora-bootc:44
FROM ${BASE_IMAGE}

# IPA client (NOT server — server is separate)
RUN dnf install -y freeipa-client \
    && dnf clean all

# Attestation infrastructure
RUN dnf install -y keylime-verifier keylime-registrar keylime-tenant \
    cosign tpm2-tools \
    && dnf clean all

# Hub services (Quadlet units for containers)
COPY quadlets/ /usr/share/containers/systemd/
COPY config/seed-policies.json /etc/arbiter/seed-policies.json
COPY config/trust-profiles/ /etc/arbiter/trust-profiles/

# enforcement-mcp
RUN dnf install -y python3-pip \
    && pip install enforcement-mcp \
    && dnf clean all

# Firstboot
COPY config/arbiter-firstboot.sh /usr/local/bin/arbiter-firstboot.sh
COPY config/arbiter-firstboot.service /etc/systemd/system/arbiter-firstboot.service
RUN systemctl enable arbiter-firstboot.service

LABEL arbiter.role=server
```

Key difference from old controller: `freeipa-client` not `freeipa-server`. Much smaller image. Faster boot.

### 7.3 Distribution Channels

| Channel | Format | Audience |
|---------|--------|----------|
| Quay.io | OCI container image (bootc) | Developers, CI/CD |
| Quay.io | qcow2 (via bootc-image-builder) | OpenStack, KVM |
| Quay.io | ISO (via bootc-image-builder) | Bare metal, edge |
| GitHub Releases | Signed checksums + cosign signatures | Verification |

---

## 8. Server Replication

### 8.1 Design Principles

Arbiter uses application-level replication between server nodes — no dependency on IPA schema extensions or external clustering tools (Patroni, BDR). The replication protocol is domain-aware: conflict resolution uses the Mubeen state machine semantics, not generic last-writer-wins.

Self-contained: Arbiter's replication is its own process (`arbiter-repl`), communicating over mTLS between server nodes. IPA provides identity (certs, DNS), not replication transport.

### 8.2 Architecture

```
┌─────────────────────────┐              ┌─────────────────────────┐
│  Arbiter Server A        │              │  Arbiter Server B        │
│                          │              │                          │
│  Hub API :8400           │              │  Hub API :8400           │
│                          │              │                          │
│  PostgreSQL              │   arbiter    │  PostgreSQL              │
│  ┌─────────────────────┐ │    -repl     │  ┌─────────────────────┐ │
│  │ workloads           │◄╪═════════════╪═►│ workloads           │ │
│  │ policies            │ │   mTLS      │  │ policies            │ │
│  │ backends            │ │   :8410     │  │ backends            │ │
│  │ enrollment_tokens   │ │  bidir sync │  │ enrollment_tokens   │ │
│  │ kbs_secrets         │ │             │  │ kbs_secrets         │ │
│  ├─────────────────────┤ │             │  ├─────────────────────┤ │
│  │ attestation_history │ │ ◄── async   │  │ attestation_history │ │
│  │ audit_log           │ │   optional  │  │ audit_log           │ │
│  └─────────────────────┘ │             │  └─────────────────────┘ │
│                          │             │                          │
│  arbiter-repl :8410      │             │  arbiter-repl :8410      │
│  keylime-verifier        │             │  keylime-verifier        │
│    (active)              │             │    (standby)             │
└─────────────────────────┘              └─────────────────────────┘
         │                                         │
         └──────────── Agents (via DNS RR) ────────┘
```

### 8.3 What Gets Replicated

| Table | Replicated | Mode | Reason |
|-------|-----------|------|--------|
| `workloads` | Yes | Sync (every 5s) | Source of truth for trust state — must be consistent |
| `policies` | Yes | Sync | All servers must enforce same policies |
| `backends` | Yes | Sync | Backend config must be consistent |
| `enrollment_tokens` | Yes | Sync | Prevent token reuse across servers |
| `webhook_registrations` | Yes | Sync | All servers fire same webhooks |
| `kbs_secrets` | Yes | Sync | Secrets available on any server (encrypted at rest) |
| `attestation_records` | Optional | Async | High volume, append-only. Each server keeps its own. Federate for queries. |
| `audit_log` | Optional | Async | High volume, append-only. Push to SIEM for central view. |

Config tables are small (hundreds to low thousands of rows). 5-second sync cycle handles this easily.

History tables are large (millions of rows over time). Each server maintains its own. Fleet-wide queries federate across servers or go through SIEM (OCSF events already implemented).

### 8.4 Conflict Resolution Rules

The Mubeen state machine makes conflicts tractable. State transitions are directional and ordered by security severity.

| Data Type | Conflict Rule | Rationale |
|-----------|--------------|-----------|
| **Workload state** | Most restrictive state wins: REVOKED > FAILED > STALE > UNDER_REMEDIATION > ATTESTING > HEALTHY > REGISTERED | Security-first. If one server saw a failure, that dominates. Attacker cannot race a HEALTHY verdict against a FAILED one. |
| **Workload metadata** | Higher lamport clock wins | Last-writer-wins for admin operations (name, tags, config). |
| **Policies** | Higher `version` wins. Same version + different content → CONFLICT flag requiring admin resolution | Policies are authored, not generated. Concurrent edits are rare and should be surfaced. |
| **Attestation records** | No conflict — append-only, each stamped with `server_id` | Both servers attest same agent → both records kept. Composite verdict merges. |
| **Audit log** | No conflict — append-only, `server_id` + `lamport_clock` | Ordered by logical clock. Consistent audit trail across servers. |
| **Enrollment tokens** | First-use wins. Token consumed on Server A → replicates as consumed → Server B rejects reuse | Single-use tokens are naturally conflict-free. |
| **Backend config** | Higher lamport clock wins | Admin operation, last-writer-wins. |

### 8.5 Replication Protocol

```
arbiter-repl daemon — runs on each server, syncs with all peers

Sync cycle (every 5s, configurable):

  1. For each peer:
     a. mTLS connect (IPA-issued certs)
     b. Exchange high-water marks:
        "I last saw seq=142 from you. You last saw seq=97 from me."
     c. Exchange repl_log entries above those marks (bidirectional, one round trip)
     d. Apply conflict resolution per table
     e. Write to local PostgreSQL
     f. Update high-water marks

  2. On reconnect after outage:
     - Catchup from last high-water mark
     - repl_log retained 7 days (configurable)
     - Gap > retention: full sync (pg_dump of config tables)

  3. Health monitoring:
     - Each peer tracked: last_sync_time, lag_seconds, status
     - Exposed at Hub API: GET /replication/status
     - Prometheus metrics: arbiter_repl_lag_seconds, arbiter_repl_peers_connected
```

### 8.6 Replication Log Schema

Every write to a replicated table appends to `repl_log`:

```sql
CREATE TABLE repl_log (
    seq         BIGSERIAL PRIMARY KEY,
    server_id   TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    operation   TEXT NOT NULL,       -- INSERT, UPDATE, DELETE
    row_id      UUID NOT NULL,
    row_data    JSONB NOT NULL,
    lamport_clock BIGINT NOT NULL,
    checksum    TEXT NOT NULL,       -- SHA-256 of row_data
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_repl_log_server_seq ON repl_log (server_id, seq);
```

Populated via PostgreSQL triggers on config tables. No application code changes needed for existing Hub API write paths — triggers capture writes transparently.

### 8.7 Peer Discovery

Two options, user chooses:

**Static** — list peers in config:
```ini
ARBITER_REPL_PEERS=arbiter-b.example.com:8410,arbiter-c.example.com:8410
```

**DNS-based** — auto-discover via IPA DNS SRV records:
```
_arbiter-repl._tcp.example.com.  SRV  0 100 8410 arbiter-a.example.com.
_arbiter-repl._tcp.example.com.  SRV  0 100 8410 arbiter-b.example.com.
```

SRV record added during `arbiter-server-install` via `ipa dnsrecord-add`. New servers join the mesh automatically.

### 8.8 Topology

Full mesh for 2-3 servers (recommended maximum):

```
     A ◄════► B              A ◄════► B
                                  ╲   ╱
                                   ╲ ╱
                                    C
     2-node mesh          3-node mesh
```

Arbiter supports up to 3 server replicas. Same practical limit IPA historically carried, sufficient for any realistic attestation deployment.

### 8.9 Keylime Verifier Failover

Keylime verifier doesn't support multi-master. Arbiter handles this:

- Active verifier runs on one server (elected via lamport clock — highest clock = leader).
- Standby verifiers are running but in read-only mode (accept agent registrations in DB but don't poll for quotes).
- On active verifier failure: standby detects via heartbeat (10s timeout), promotes itself, begins polling agents.
- Agent registrations are in the replicated `workloads` table — standby already has complete agent list.
- Quote history stays local per-server. Standby starts fresh on history but immediately re-attests all agents.
- Failover gap: agents go STALE for one TTL cycle (~5-60 min depending on tier), then re-attest against new verifier. No config data loss.

### 8.10 Adding a Server Replica

```bash
# On new node:
ipa-client-install --server=idm.example.com --domain=example.com -p admin -w <pw> -U
arbiter-server-install \
    --ipa-server=idm.example.com \
    --replica-of=arbiter-a.example.com

# arbiter-server-install does:
#   1. Register DNS SRV record for _arbiter-repl._tcp
#   2. Full sync from existing server (pg_dump of config tables)
#   3. Start Hub API, keylime-verifier (standby), arbiter-repl
#   4. Register DNS A record for arbiter.example.com (round-robin)
#   5. First repl sync cycle within 5s
```

Two commands. Same pattern as `ipa-replica-install`.

### 8.11 Agent Behavior During Server Failover

| Agent Component | Server Down Behavior | On Recovery |
|-----------------|---------------------|-------------|
| keylime-agent | Continues running. Collects TPM quotes locally. Re-attestation calls fail. | Re-attests against new active verifier. Returns to HEALTHY. |
| Falco | Continues monitoring. Alerts queue in local journal. | Queued alerts delivered to Hub API. |
| OpenShell | Sandboxes keep running. No new workload enrollment. | Enrollment resumes. |
| linux-mcp-server | Unaffected. Local operations continue. | No action needed. |
| IPA client | Unaffected — enrolled against IdM, not Arbiter. | No action needed. |

Workloads transition to STALE (not FAILED) when TTL expires during outage. On recovery, agents re-attest and return to HEALTHY automatically. No manual intervention.

### 8.12 Replication Security

| Concern | Mitigation |
|---------|-----------|
| Repl traffic intercepted | mTLS with IPA-issued certs. Both sides validate against IPA CA. |
| Rogue server joins mesh | Must have valid IPA service principal + DNS SRV record. IPA admin controls both. |
| Repl log tampering | Checksum (SHA-256) on each entry. Receiving server validates before applying. |
| Split-brain (network partition) | Most-restrictive-state-wins rule ensures security-safe resolution on reconnect. A workload marked FAILED on one side stays FAILED after merge. |
| Replay attack on repl stream | Lamport clock + sequence numbers. Duplicate entries rejected. |

---

## 9. Deployment Scenarios

### 9.1 Greenfield (No Existing IdM)

```
Step 1: Boot IdM Primary image (idm-image-mode)
        Config: domain, realm, admin password, DS password
        Wait: ~10 min

Step 2: Boot Arbiter Server image
        Config: IdM server FQDN, domain, admin password
        Wait: ~5-8 min

Step 3: Boot N Arbiter Agent images
        Config: Arbiter Server FQDN, IdM server FQDN, enrollment token
        Wait: ~3 min each

Total: ~18 min for a 3-node cluster (IdM + server + 1 agent)
```

### 9.2 Brownfield (Existing IdM)

```
Step 1: Boot Arbiter Server image
        Config: existing IdM server FQDN, domain, admin password
        Wait: ~5-8 min

Step 2: Boot N Arbiter Agent images
        Config: Arbiter Server FQDN, IdM server FQDN, enrollment token
        Wait: ~3 min each

Total: ~8-11 min (IdM already exists)
```

### 9.3 Replicated (HA)

```
Step 1: Boot IdM Primary (or use existing)

Step 2: Boot Arbiter Server A
        Config: IdM server FQDN, domain, admin password
        Wait: ~5-8 min

Step 3: Boot Arbiter Server B (replica)
        ipa-client-install + arbiter-server-install --replica-of=arbiter-a.example.com
        Wait: ~3-5 min (no IPA server install, just client + sync)

Step 4: Boot N Arbiter Agent images
        Agents discover both servers via DNS round-robin
        Wait: ~3 min each

Total: ~16 min for HA setup (IdM + 2 servers + 1 agent)
       Agents auto-failover between servers via DNS
```

### 9.4 Satellite-Managed

```
Step 1: Arbiter Server provisioned via Satellite (host group + activation key)
Step 2: Agent provisioned via Satellite (different host group, enrollment token in activation key)
Step 3: Satellite auto-enrolls agents, no manual token copy

Total: standard Satellite provisioning time + ~3-5 min firstboot
```

---

## 10. Open Questions

1. **Replication in v1?** Core `arbiter-repl` daemon + conflict resolution rules + repl_log triggers. Single-server deployments work without it (daemon doesn't start when no peers configured). Multi-server needs sync protocol, failover testing, split-brain validation. Estimate: 2-3 weeks for v1 replication.

2. **Subscription model?** Own subscription or included with RHEL/Satellite?

3. **Agent on non-bootc hosts?** `dnf install arbiter-agent` path alongside bootc image? Some customers will not re-image existing VMs.

4. **Appliance sizing?** Server (keylime-verifier + Hub + DB on one node) — likely 4 vCPU / 8GB minimum. Agent lighter — 2 vCPU / 4GB. Needs benchmarking.

5. **IdM version requirements?** ahdapa requires IPA 4.12+ (Fedora 40+ / RHEL 10). RHEL 8 IdM (IPA 4.9) not supported. RHEL 9 IdM (IPA 4.11) may work for SPNEGO-only auth but is untested.

---

## Appendix A: Comparison — Current vs Appliance

| Dimension | Current (5 VMs, 20 playbooks) | Appliance (3 images) |
|-----------|-------------------------------|---------------------|
| IdM dependency | Embedded in controller | Separate, bring-your-own or deploy fresh |
| Config values (server) | ~40 across playbooks | 3 required, ~10 optional |
| Config values (agent) | ~15 across playbooks | 3 required, 1 optional |
| Time to deploy (with IdM) | ~45 min + manual steps | ~18 min total |
| Time to deploy (existing IdM) | ~30 min + manual steps | ~11 min total |
| VMs required | 5 (builder + primary + replica + hub + agent) | 3 (IdM + server + agent) |
| Registry login | Manual per-node | Baked into image or not needed |
| Cert distribution | Ansible copies certs between nodes | IPA CA auto-distributes; keylime auto-generates |
| Backend config | Per-component env vars | Auto-detection |
| Auth setup | Manual OIDC client registration | Firstboot registers with IdM's ahdapa |
| Upgrade path | Re-run playbooks | `bootc upgrade` + `bootc rollback` |
| Air-gap support | No (runtime container pulls) | Yes (self-contained image) |
| Identity blast radius | Controller compromise = IPA + Arbiter | Arbiter Server compromise ≠ IPA admin |
| Server HA | None (single point of failure) | arbiter-repl: up to 3 servers, domain-aware conflict resolution, automatic keylime failover |

---

## Appendix B: Glossary

| Term | Meaning |
|------|---------|
| **bootc** | Boot container — immutable OS with read-only `/usr`, mutable `/etc` and `/var` |
| **Quadlet** | Podman's native systemd generator for container units |
| **ahdapa** | IPA-native OIDC/OAuth2 provider |
| **Mubeen** | Arbiter Hub's 7-state workload lifecycle state machine |
| **Trust tier** | Pre-validated security profile bundle (sovereign / verified / untrusted) |
| **OCSF** | Open Cybersecurity Schema Framework — standard event format |
| **EDA** | Event-Driven Ansible — rulebook-based automation |
| **SPNEGO** | Simple and Protected GSSAPI Negotiation — HTTP Kerberos authentication |
| **arbiter-repl** | Arbiter's native replication daemon — syncs config state between server nodes via mTLS |
| **Lamport clock** | Logical clock for ordering events across distributed servers without synchronized wall clocks |
| **repl_log** | Append-only replication log in PostgreSQL, populated by triggers on config tables |
