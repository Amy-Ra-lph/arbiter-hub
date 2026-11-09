# Arbiter Hub — Design Partner Onboarding Guide

## Executive Summary

This guide walks you through deploying the Arbiter Hub stack in your data center. When complete, you will have:

- **Identity Management**: FreeIPA with OAuth2/OIDC (ahdapa) and ACME CA (akamu)
- **Attestation Hub**: Workload trust management with Keylime, Trustee, cosign, and Rekor
- **Post-Quantum Cryptography**: Full ML-DSA-65 certificate chain from your RHCS root CA
- **Workload Enrollment**: Container, VM, bare-metal, and edge device onboarding
- **CI/CD Integration**: GitHub Actions attestation gate
- **ITSM Integration**: ServiceNow incident creation from trust violations

**Time estimate**: 3-4 hours for a 3-node cluster, plus 1-2 hours for PQC configuration.

## Prerequisites

### Hardware

| Node | Role | RAM | vCPU | Disk | Purpose |
|------|------|-----|------|------|---------|
| 1 | IPA Primary | 8 GB | 2 | 40 GB | Identity, OAuth2, ACME CA, PQC |
| 2 | Arbiter Hub | 4 GB | 2 | 20 GB | Attestation, signing, EDA |
| 3+ | Agent | 2 GB | 1 | 20 GB | Workloads, TPM attestation |

### Network

- All nodes must be able to reach each other by FQDN
- Assign DNS names before deployment (e.g., `ipa.example.corp`, `hub.example.corp`)
- If using IPA DNS (recommended), only the IPA node needs a pre-existing DNS entry
- Ports: 22 (SSH), 80/443 (HTTP/HTTPS), 88/464 (Kerberos), 389/636 (LDAP), 8400-8402 (Hub), 5001 (EDA)

### Software

- **RHCS root CA** with ML-DSA support (latest RHCS release) — required for PQC
- **KVM host** with `virt-install` (for KVM deployment) — or VMware/OpenStack (image-only path)
- **Rust 1.89+** on one build host (for kuipa build from source — no pre-built packages yet)

### Credentials

You will need:
- RHCS admin credentials (for subordinate CA enrollment)
- DNS server admin access (if not using IPA DNS)
- SSH key pair for node access

## Architecture

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                     Your Data Center                             │
 │                                                                  │
 │  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐     │
 │  │  IPA Primary  │   │  Arbiter Hub │   │  Agent Node(s)   │     │
 │  │              │   │              │   │                  │     │
 │  │  FreeIPA     │   │  Hub API     │   │  arbiter-agent   │     │
 │  │  ahdapa OIDC │   │  Hub MCP     │   │  keylime_agent   │     │
 │  │  akamu CA    │◄──│  Hub UI      │──►│  IPA client      │     │
 │  │  kuipa       │   │  Keylime     │   │  kuipa           │     │
 │  │  RHCS sub-CA │   │  Trustee     │   │  workloads...    │     │
 │  └──────────────┘   │  cosign      │   └──────────────────┘     │
 │         ▲           │  Rekor       │            ▲                │
 │         │           └──────────────┘            │                │
 │  ┌──────┴──────────────────┴────────────────────┴──────┐        │
 │  │              Kerberos / SPNEGO / DNS                 │        │
 │  └─────────────────────────────────────────────────────┘        │
 │                                                                  │
 │  ┌──────────────┐                                                │
 │  │  RHCS Root   │  (your existing CA — ML-DSA enabled)           │
 │  │  CA Server   │                                                │
 │  └──────────────┘                                                │
 └──────────────────────────────────────────────────────────────────┘
```

### Authentication Flow

```
Agent → SPNEGO (Kerberos keytab) → Hub API → verify via IPA KDC
Human → ahdapa (OIDC/PKCE) → Hub UI → JWT bearer to API
CI/CD → ahdapa (client_credentials) → Hub API → service token
```

### PQC Certificate Chain

```
RHCS Root CA (ML-DSA)
  └─► akamu subordinate CA (ML-DSA-65)
        └─► End-entity certs (ML-DSA-65)
              ├── Node TLS certificates
              ├── Workload identity certs
              └── Code signing certs (cosign)
```

## Quickstart Deployment

### Step 1: Configure

```bash
cd deploy/partner/
cp site.env.example site.env
```

Edit `site.env` with your site-specific values. Required fields:

| Field | Example | Description |
|-------|---------|-------------|
| `SITE_DOMAIN` | `example.corp` | DNS domain for all nodes |
| `SITE_REALM` | `EXAMPLE.CORP` | Kerberos realm (uppercase domain) |
| `ADMIN_PASSWORD` | (set yours) | IPA admin password |
| `DS_PASSWORD` | (set yours) | Directory Server password |
| `IPA_HOSTNAME` | `ipa.example.corp` | IPA node FQDN |
| `HUB_HOSTNAME` | `hub.example.corp` | Hub node FQDN |
| `SIGNING_HOSTNAME` | `signing.example.corp` | Signing node FQDN |
| `AGENT_HOSTNAMES` | `agent1.example.corp` | Space-separated agent FQDNs |
| `DNS_FORWARDER` | `10.0.0.1` | Upstream DNS resolver |
| `RHCS_CA_URL` | `https://ca.example.corp:8443` | RHCS root CA URL |

See `site.env.example` for all fields including PQC options.

### Step 2: Deploy

```bash
# KVM deployment (recommended for evaluation)
./deploy.sh --site-env=site.env --target=kvm

# Bare-metal (generates kickstart files)
./deploy.sh --site-env=site.env --target=bare-metal

# Image-only (generates cloud-init user-data for VMware/OpenStack)
./deploy.sh --site-env=site.env --target=image-only

# Air-gapped (from pre-downloaded bundle)
./deploy.sh --site-env=site.env --target=kvm --offline --images-dir=images/
```

Nodes deploy in order: IPA → Hub → Signing → Agent(s). Each waits for the previous node's firstboot to complete.

### Step 3: Verify

```bash
./verify-deployment.sh --site-env=site.env
```

This runs 36 checks across all nodes. All should pass for a healthy deployment.

## PQC Configuration

After the base deployment, configure the post-quantum certificate chain:

```bash
./setup-pqc.sh --site-env=site.env
```

This script:
1. Generates an ML-DSA-65 CSR for akamu as a subordinate CA
2. Submits the CSR to your RHCS root CA
3. Configures akamu with the signed certificate
4. Enrolls agent nodes with kuipa for PQ credential lifecycle

**Note**: The CSR approval step may require manual action in your RHCS admin console, depending on your approval policy.

### Known limitation

`kuipa protect` (sealed keytabs using ML-KEM-768 wrapping) is blocked on an upstream ACI patch. Use `kuipa enroll` without sealing for now.

## Workload Onboarding

Enroll workloads with both IPA (identity) and Hub (attestation):

```bash
# Container workload
./onboard-workload.sh --type=container --name=my-app \
  --image=registry.example.corp/my-app:v1

# VM workload (run on the VM itself)
./onboard-workload.sh --type=vm --name=db-server

# Bare-metal workload
./onboard-workload.sh --type=bare-metal --name=web-server

# Edge device (supports intermittent connectivity)
./onboard-workload.sh --type=edge --name=sensor-01
```

Each type follows a different enrollment path, but all end with the workload registered in both IPA and Hub. See `onboard-workload.sh --help` for all options.

### Workload State Machine

After enrollment, Hub tracks each workload through these states:

```
REGISTERED → ATTESTING → ATTESTED → HEALTHY
                                  ↕
                              SUSPECT → QUARANTINED → REVOKED
```

## Integration Patterns

### GitHub Actions

Copy `integrations/github-actions-attest-deploy.yml` to `.github/workflows/` in your repository. Configure:

1. **Self-hosted runner** with network access to Hub and IPA
2. **Repository secrets**: `ARBITER_CLIENT_ID`, `ARBITER_CLIENT_SECRET` (ahdapa OAuth2 client)
3. **Repository variables**: `IPA_HOST`, `HUB_HOST`, `REGISTRY`
4. **Branch protection**: require the `verify-attestation` job to pass before merge

The workflow: builds → signs (cosign via Hub) → registers (Hub API) → verifies attestation state → deploys only if ATTESTED or HEALTHY.

### ServiceNow

Run the webhook receiver on a host reachable from Hub:

```bash
export SNOW_INSTANCE=your-instance.service-now.com
export SNOW_USER=api_user
export SNOW_PASSWORD=api_password
python3 integrations/servicenow-webhook.py --port 8080
```

Configure Hub EDA to send webhooks to `http://<receiver-host>:8080/webhook`. Events for SUSPECT, QUARANTINED, and REVOKED states automatically create ServiceNow incidents.

## Known Gaps

| Gap | Impact | Workaround |
|-----|--------|------------|
| kuipa `protect` needs upstream ACIs | Sealed keytabs unavailable | Use `kuipa enroll` without sealing |
| kuipa built from source (Rust 1.89+) | Need Rust toolchain | Build script + deps list provided |
| Hub nginx TLS internal | API traffic unencrypted hub-internal | Pods on same host, localhost only |
| http-01 ACME blocked in RFC1918 | Can't use ACME for internal certs | Use akamu CLI direct issuance |
| cosign OIDC client not in ahdapa | cosign keyless needs manual setup | Register client in clients.toml |

## Troubleshooting

### ahdapa returns 503

Check: SELinux policy loaded (`semodule -l | grep ahdapa`), httpd proxy config exists (`/etc/httpd/conf.d/ipa-idp-proxy.conf`), ahdapa socket exists (`/run/ahdapa/ahdapa.sock`), httpd restarted after config changes.

### Keylime attestation fails

Check: TPM device available (`ls /dev/tpm0` or swtpm running), keylime_agent enrolled with verifier, IMA policy loaded (if using IMA).

### Hub API unreachable

Check: firewall allows port 8400, Hub firstboot completed (`/var/lib/arbiter-hub/.firstboot-complete`), nginx running.

### kuipa enrollment fails

Check: Rust 1.89+ installed, IPA server reachable, Kerberos TGT valid (`klist`).

## Appendix: site.env Reference

See `site.env.example` for the complete list of configuration fields with descriptions and defaults.

## Appendix: API Endpoints

| Endpoint | Port | Auth | Purpose |
|----------|------|------|---------|
| Hub API | 8400 | SPNEGO / Bearer | Workload CRUD, state, signing |
| Hub MCP | 8401 | Bearer | Read-only agent/AI queries |
| Hub UI | 8402 | OIDC (ahdapa) | Web dashboard |
| EDA | 5001 | Webhook secret | Event-driven automation |
| ahdapa | 443 `/idp/` | OIDC / Kerberos | OAuth2/OIDC provider |
| akamu | 443 `/acme/` | ACME protocol | PQC certificate issuance |
| IPA | 443 `/ipa/` | Kerberos / password | Identity management |
