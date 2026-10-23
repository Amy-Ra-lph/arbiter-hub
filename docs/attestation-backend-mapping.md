# Attestation Backend Mapping

How Arbiter Hub assigns attestation backends to workloads, and how to extend the mapping for new platforms.

## Backend Inventory

| Backend | What it proves | Requires on target | Evidence |
|---|---|---|---|
| **keylime** | Host integrity — boot chain + file hashes | TPM 2.0 (hw or swtpm) + Keylime agent | IMA log, PCR quotes |
| **measured_boot** | Launch integrity — firmware through kernel | TPM 2.0, PCR 11 policy | PCR values against reference |
| **cosign** | Image provenance — who built it, untampered | Container image in registry | Sigstore signature + transparency log |
| **falco** | Runtime behavior — no anomalous activity | Falco w/ eBPF (kernel ≥ 5.8) | Syscall/file/network rule verdicts |

## Current Mapping (v0.1.0)

| Workload type | Example | Backends | Why |
|---|---|---|---|
| `service` (host daemon) | Demo Good Workload, E2E Test | keylime | Host-level: TPM proves the OS is unmodified |
| `service` (container) | Enforcement MCP, Linux MCP | cosign + falco | Image signature proves provenance; Falco watches runtime |
| `service` (both) | Demo Bad Workload | keylime + falco | Host TPM + runtime monitoring |
| `agentic` (sandbox) | OpenShell wid-sovereign/verified/untrusted | falco + keylime | Sandboxes need runtime containment proof + host integrity |
| `bootc` (sealed image) | Bootc Sealed Image Demo | cosign | Immutable image — only provenance matters, no runtime agent |
| `cvm` (confidential VM) | (not yet enrolled) | measured_boot | TEE launch measurement via PCR 11 |

## IdM Client Systems as Workloads

IPA-enrolled clients are a natural fit — they already have a Kerberos principal (`host/<fqdn>@REALM`), HBAC policies, and a trust relationship with the IPA server. Arbiter Hub can leverage this identity directly for enrollment without additional credential provisioning.

### IdM client workload types

| Client type | Example | ipa_principal | Recommended backends | Rationale |
|---|---|---|---|---|
| **RHEL IdM client (physical)** | Data center server enrolled via `ipa-client-install` | `host/db01.idm.example.com@IDM.EXAMPLE.COM` | keylime + falco | HW TPM for host integrity; Falco for runtime if workload is security-sensitive |
| **RHEL IdM client (VM)** | vSphere/KVM VM with IPA enrollment | `host/web03.idm.example.com@IDM.EXAMPLE.COM` | keylime | vTPM proves IMA integrity; Falco optional based on workload tier |
| **IdM client running containers** | Podman host enrolled in IPA, running app containers | `host/app-host.idm.example.com@IDM.EXAMPLE.COM` | keylime + cosign + falco | Host TPM + container image provenance + runtime anomaly detection |
| **IdM-enrolled edge node** | Remote site RHEL with IPA client, intermittent WAN | `host/branch-gw.idm.example.com@IDM.EXAMPLE.COM` | keylime | Works offline; Keylime agent local. Cosign needs registry, skip for disconnected |
| **IdM client (Image Mode)** | bootc system with IPA enrollment baked into image | `host/imgmode-01.idm.example.com@IDM.EXAMPLE.COM` | keylime + cosign | Image signature + runtime TPM. measured_boot if PCR policy active |
| **IPA server / replica** | The IPA infrastructure itself as a workload | `host/ipa.idm.example.com@IDM.EXAMPLE.COM` | keylime + measured_boot | Highest-value target — boot chain + IMA. Falco if audit footprint is acceptable |
| **Trust agent (AD trust)** | IPA server with `ipa-adtrust-install` | `host/ipa-trust.idm.example.com@IDM.EXAMPLE.COM` | keylime + measured_boot + falco | Cross-realm trust node — full stack attestation |

### kuipa integration (PQ credential protection)

AB's [kuipa](https://github.com/abbra/kuipa) project adds a post-quantum credential lifecycle layer for IPA-enrolled hosts. It is **not an attestation backend** — it protects the identity credentials that attestation verifies against. See [kuipa-integration-map.md](kuipa-integration-map.md) for full integration design.

Key implications for backend mapping:

| kuipa feature | Effect on attestation | Backend interaction |
|---|---|---|
| `kuipa protect` (sealed keytab) | Identity bound to IPA server set — VM clone can't unseal keytab | Complements keylime: TPM proves OS, kuipa proves credential binding |
| Blind voucher enrollment | Orchestrator never sees keytab — reduced blast radius | Enrollment flow: voucher → IPA principal → Arbiter Hub auto-enroll |
| `kuipa rekey` (forward secrecy) | Key rotation without re-enrollment | Transparent to attestation — workload stays HEALTHY |
| PQ Tang (`tang-pqc`) | ML-KEM disk encryption for bootc/Image Mode | Strengthens cosign-only workloads with at-rest protection |
| `kuipa check` (future signal) | Credential health: can host unseal? servers reachable? | Potential lightweight signal alongside keylime/falco |

For kuipa-enabled IdM clients, add `kuipa protect` to post-enrollment playbooks. The keytab sealing is orthogonal to backend selection — every backend combination benefits from it.

### Enrollment advantage for IdM clients

IdM clients already have what other workload types must provision:

1. **Identity** — `host/<fqdn>@REALM` principal exists in IPA. Arbiter Hub uses this directly as `ipa_principal` during enrollment — no separate credential issuance.
2. **Authentication** — Keytab at `/etc/krb5.keytab` enables the workload to authenticate to the Hub API via GSSAPI/SPNEGO, or obtain an OIDC token via ahdapa device-code flow.
3. **Authorization** — HBAC rules in IPA can gate which hosts are permitted to enroll with specific backend types or policy tiers.
4. **Certificate** — IPA Certmonger manages host certificates, providing mTLS identity for Keylime agent ↔ verifier communication.
5. **DNS** — IPA DNS provides SRV records; the enrollment playbook can discover the Hub endpoint via `_arbiter._tcp.idm.example.com`.

### Automated enrollment for IdM fleet

```yaml
# Ansible playbook: enroll all IPA clients as Arbiter workloads
- name: Enroll IdM clients in Arbiter Hub
  hosts: ipaclients
  vars:
    hub_url: "https://hub.arbiter.demo/api"
    default_backends:
      - keylime
  tasks:
    - name: Get IPA principal
      command: klist -k /etc/krb5.keytab
      register: keytab_out

    - name: Extract host principal
      set_fact:
        host_principal: "{{ keytab_out.stdout_lines | select('match', '.*host/.*') | first | regex_replace('.*\\s+(host/.*)$', '\\1') }}"

    - name: Check TPM
      stat: path=/dev/tpm0
      register: tpm_check

    - name: Check Keylime agent
      systemd: name=keylime_agent
      register: keylime_check
      ignore_errors: true

    - name: Check Falco
      systemd: name=falco
      register: falco_check
      ignore_errors: true

    - name: Build backend list
      set_fact:
        backends: >-
          {{
            (['keylime'] if tpm_check.stat.exists and keylime_check.status.ActiveState == 'active' else [])
            + (['falco'] if falco_check.status.ActiveState == 'active' else [])
            + (['cosign'] if container_host | default(false) else [])
          }}

    - name: Obtain OIDC token via ahdapa
      uri:
        url: "https://idm.example.com/idp/token"
        method: POST
        body_format: form-urlencoded
        body:
          grant_type: "urn:ietf:params:oauth:grant-type:device_code"
          client_id: "arbiter-hub-enrollment"
          device_code: "{{ device_code }}"
      register: token_response
      when: use_oidc | default(false)

    - name: Register with Arbiter Hub
      uri:
        url: "{{ hub_url }}/workloads"
        method: POST
        headers:
          Authorization: "Bearer {{ token_response.json.access_token | default(arbiter_token) }}"
        body_format: json
        body:
          ipa_principal: "{{ host_principal }}"
          display_name: "{{ inventory_hostname }}"
          workload_type: "service"
          backend_types: "{{ backends | default(default_backends) }}"
          platform_hint: "idm-client"
        status_code: [200, 201, 409]
      register: enroll_result

    - name: Report
      debug:
        msg: "{{ 'Already enrolled' if enroll_result.status == 409 else 'Enrolled with backends ' + (backends | join('+')) }}"
```

### HBAC-gated enrollment tiers

IPA HBAC rules can enforce which hosts get which attestation tier:

| HBAC service | Host group | Backends permitted | Use case |
|---|---|---|---|
| `arbiter-tier-1` | `idm-servers` | keylime + measured_boot + falco | Infrastructure nodes — full attestation |
| `arbiter-tier-2` | `app-servers` | keylime + falco | Application tier — host + runtime |
| `arbiter-tier-3` | `edge-nodes` | keylime | Edge — TPM only, minimal overhead |
| `arbiter-tier-4` | `dev-workstations` | falco | Dev — runtime monitoring only |

The Hub enrollment endpoint can query IPA HBAC to determine which tier a host belongs to and auto-select backends accordingly, without the caller needing to specify `backend_types`.

## Extended Mapping — Edge & New Platforms

| Platform | Form factor | Recommended backends | Rationale |
|---|---|---|---|
| **RHEL Image Mode (bare metal)** | Immutable OS, hw TPM | measured_boot + keylime | HW TPM available; measured_boot proves boot chain, keylime proves IMA file integrity at runtime |
| **RHEL Image Mode (VM)** | Immutable OS, vTPM | keylime + cosign | vTPM for IMA; cosign verifies the bootc image was signed before deployment |
| **RHEL Image Mode (edge, disconnected)** | Bare metal, intermittent network | keylime | Keylime agent runs locally even offline; cosign needs registry access at verify time |
| **MicroShift (edge K8s)** | K8s workloads on edge node | cosign + falco + keylime | Three layers: host (keylime), workload images (cosign), runtime (falco) |
| **Satellite-managed fleet** | RHEL hosts, foreman_arbiter | keylime | TPM attestation via foreman_arbiter plugin sub-status; cosign if content from Quay |
| **IoT / constrained device** | ARM SBC, no TPM | cosign | No TPM means no keylime; verify the firmware/OS image signature only |
| **AAP Execution Environment** | Ansible EE container | cosign + falco | Signed EE image + runtime anomaly detection during playbook execution |
| **CVM on public cloud** | Azure CVM / AWS Nitro | measured_boot | Cloud attestation report (SNP/TDX/Nitro) mapped to measured_boot backend |
| **Developer laptop (OpenShell)** | Podman sandbox | falco | No TPM guarantee; Falco eBPF proves the sandbox stayed within policy |

## Capability Detection for Automated Onboarding

When a workload registers, the enrollment request or the enrollment pipeline can probe for platform capabilities and select backends automatically.

### Detection signals

| Capability | How to detect | Backend it enables |
|---|---|---|
| TPM 2.0 present | `/dev/tpm0` exists or `tpm2_getcap properties-fixed` succeeds | keylime, measured_boot |
| Keylime agent running | `systemctl is-active keylime_agent` or agent API responds on 9002 | keylime |
| eBPF capable | Kernel ≥ 5.8 + `bpf()` syscall permitted | falco |
| Falco running | `systemctl is-active falco` or gRPC API responds | falco |
| Container image | `artifact_ref` field set in enrollment request | cosign |
| Image signed | `cosign verify` against configured key succeeds | cosign |
| PCR policy active | Keylime verifier reports PCR 11 evaluation | measured_boot |
| Confidential VM | `/sys/kernel/security/sev` or CPUID flag for TDX/SEV-SNP | measured_boot |

### Proposed enrollment flow

```
POST /workloads
  ipa_principal: "host/edge-01.example.com@EXAMPLE.COM"
  display_name: "Edge Gateway 01"
  workload_type: "service"
  platform_hint: "image-mode-bare-metal"   # optional hint
  # backend_types omitted → auto-select
```

When `backend_types` is omitted in the registration request, the API selects backends using this precedence:

1. **Explicit list** — caller specifies `backend_types: ["keylime", "cosign"]` → use as-is, fail if any backend not configured.
2. **Platform hint** — caller provides `platform_hint` → look up the recommended set from a policy table (below). Override with explicit list if both present.
3. **Capability probe** — enrollment pipeline SSHs or agents to the target, runs detection commands, returns a capability set. API maps capabilities to backends.
4. **Default** — if nothing else, assign all healthy backends whose prerequisites the workload type satisfies.

### Policy table (configurable)

```yaml
# deploy/config/backend-policy.yaml
backend_policy:
  platform_hints:
    image-mode-bare-metal:
      backends: [measured_boot, keylime]
      minimum: 2
    image-mode-vm:
      backends: [keylime, cosign]
      minimum: 1
    image-mode-edge-disconnected:
      backends: [keylime]
      minimum: 1
    microshift:
      backends: [cosign, falco, keylime]
      minimum: 2
    satellite-managed:
      backends: [keylime]
      minimum: 1
    container:
      backends: [cosign, falco]
      minimum: 1
    cvm:
      backends: [measured_boot]
      minimum: 1
    agentic-sandbox:
      backends: [falco, keylime]
      minimum: 1
    bootc-sealed:
      backends: [cosign]
      minimum: 1
    iot-constrained:
      backends: [cosign]
      minimum: 1

  workload_type_defaults:
    service: [keylime]
    agentic: [falco, keylime]
    bootc: [cosign]
    cvm: [measured_boot]

  # Minimum backends required for any workload to be considered attestable
  global_minimum: 1
```

### Enrollment pipeline automation (Ansible)

The CI enrollment playbook (`deploy/ansible/enroll-workloads.yml`) can automate detection:

```yaml
- name: Detect attestation capabilities
  hosts: workload_targets
  tasks:
    - name: Check TPM
      stat: path=/dev/tpm0
      register: tpm_check

    - name: Check Keylime agent
      systemd: name=keylime_agent
      register: keylime_check
      ignore_errors: true

    - name: Check Falco
      systemd: name=falco
      register: falco_check
      ignore_errors: true

    - name: Check kernel version for eBPF
      shell: uname -r | awk -F. '{print ($1 * 100) + $2}'
      register: kernel_ver

    - name: Build capability set
      set_fact:
        attestation_backends: >-
          {{
            (['keylime'] if tpm_check.stat.exists and keylime_check.status.ActiveState == 'active' else [])
            + (['falco'] if falco_check.status.ActiveState == 'active' else [])
            + (['cosign'] if artifact_ref is defined else [])
            + (['measured_boot'] if tpm_check.stat.exists and pcr_policy | default(false) else [])
          }}

    - name: Register with Arbiter Hub
      uri:
        url: "https://hub.example.com/api/workloads"
        method: POST
        headers:
          Authorization: "Bearer {{ arbiter_token }}"
        body_format: json
        body:
          ipa_principal: "{{ ansible_fqdn_principal }}"
          display_name: "{{ inventory_hostname }}"
          workload_type: "{{ workload_type | default('service') }}"
          backend_types: "{{ attestation_backends }}"
```

### EDA integration

Event-Driven Ansible can react to new host provisioning and trigger enrollment:

```yaml
# EDA rulebook: auto-enroll on Satellite host registration
- name: Auto-enroll new hosts
  condition: event.type == "host_created" and "arbiter" in event.hostgroup
  action:
    run_playbook:
      name: deploy/ansible/enroll-workloads.yml
      extra_vars:
        workload_targets: "{{ event.hostname }}"
```

## Decision Matrix

For choosing backends when designing a new workload type:

```
Is the host IPA-enrolled?
├── Yes → use ipa_principal directly, check HBAC tier
│   └── (proceed to TPM check below — IPA gives you identity, not attestation)
└── No → provision identity separately (service account, device-code flow)

Is there a TPM (hw or vTPM)?
├── Yes → keylime (baseline)
│   ├── Boot chain matters? → + measured_boot
│   ├── Runtime behavior matters? → + falco (if eBPF capable)
│   └── IPA server or trust agent? → + measured_boot (high-value target)
└── No
    ├── Container image? → cosign
    │   └── Long-running? → + falco
    └── Neither → cosign on the OS image if available, else not attestable
```

Single backend is acceptable for constrained environments. Two or more backends provide defense in depth — one proves provenance, another proves current-state integrity.

For IdM fleets specifically: the enrollment cost is near-zero because identity and authentication already exist. The main decision is which attestation depth (tier 1-4) each host group warrants based on its role and blast radius.
