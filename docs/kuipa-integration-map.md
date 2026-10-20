# kuipa ↔ Arbiter Hub Integration Map

kuipa is AB's client-side identity lifecycle tool for IPA-enrolled cloud/VM workloads.
This document maps kuipa capabilities to Arbiter Hub components and identifies
integration points for the agentic security demo stack.

## Feature Mapping

| kuipa Feature | Description | Arbiter Component | Integration |
|---|---|---|---|
| **Voucher enrollment** | Blind identity issuance — orchestrator never sees which agent gets credential | Workload onboarding (`POST /api/v1/workloads`) | Auto-enroll on agent registration; voucher ties IPA host principal to workload UUID |
| **`kuipa protect`** | Seals keytab to TPM PCR values | Keylime TPM attestation | Sealed keytab only decrypts when PCR values match Keylime-verified state |
| **PQ Tang (`kuipad`)** | ML-KEM-768 network-bound volume encryption | Akamu PQC CA | Shares ML-KEM key infrastructure; encrypted agent data stores |
| **vTPM binding** *(planned)* | Keytab locked to specific TPM EK | Keylime `swtpm` / hardware TPM | Direct bridge — sealed identity only opens with *this* TPM's endorsement key |
| **`kuipa seal`** | User-space encrypted secret vaults | Trust tiers (sovereign/verified/untrusted) | Sovereign-tier agents get kuipa-sealed credentials; lower tiers cannot unseal |
| **Termination cleanup** | `ipa host-del` destroys all sealed creds | EDA remediation playbooks | Revocation triggers: `kuipa cleanup` → keytab + sealed vaults wiped instantly |

## Security Narratives

### Snapshot Useless
Even if an attacker clones the VM, TPM-sealed credentials do not transfer.
The cloned VM has different PCR values → kuipa-protected keytab refuses to unseal →
Keylime attestation fails → Arbiter Hub marks workload `FAILED` →
EDA fires quarantine playbook.

### Bounded Orchestrator Damage
Blind voucher pattern means a compromised orchestrator (e.g., AAP controller)
cannot enumerate or steal agent identities. Each agent enrolls via a single-use
voucher; the orchestrator sees the voucher handle but never the resulting keytab.

### Defense-in-Depth Stack

```
Layer 1: kuipa protect     — credential at rest (TPM-sealed keytab)
Layer 2: Keylime           — platform integrity (continuous PCR/IMA verification)
Layer 3: Falco             — runtime behavior (eBPF syscall monitoring)
Layer 4: Arbiter Hub       — federation control plane (state machine, webhooks)
Layer 5: EDA               — automated response (quarantine/revoke/re-attest)
Layer 6: IPA + ahdapa      — identity governance (HBAC, OAuth2, trust tiers)
```

## Lifecycle Sequence

```
1. Agent VM boots
   └─ swtpm starts (TPM emulation)
   └─ Keylime agent registers with verifier

2. Workload onboarding
   └─ Arbiter Hub creates workload record (REGISTERED)
   └─ kuipa voucher enrollment → IPA host principal created
   └─ kuipa protect → keytab sealed to current PCR values

3. Attestation loop
   └─ Keylime verifier polls PCR + IMA continuously
   └─ Arbiter Hub polls verifier → HEALTHY state
   └─ Trust tier promotion: untrusted → verified → sovereign
   └─ Sovereign tier: kuipa seal unlocks additional secrets

4. Anomaly detected
   └─ Falco eBPF alert → Arbiter Hub webhook
   └─ State: HEALTHY → SUSPECT → QUARANTINED
   └─ EDA playbook: network fence + credential freeze

5. Revocation
   └─ Arbiter Hub: QUARANTINED → REVOKED
   └─ EDA: ipa user-disable + ipa host-del
   └─ kuipa termination cleanup: sealed creds destroyed
   └─ Keylime: agent removed from verifier

6. Re-attestation (if recoverable)
   └─ Fresh kuipa voucher → new keytab → re-seal to TPM
   └─ Keylime re-registers → Arbiter Hub: REGISTERED → ATTESTING → HEALTHY
```

## Implementation Status

| Integration Point | Status | Notes |
|---|---|---|
| Voucher enrollment | **Planned** | Requires kuipa server-side component on IPA host |
| `kuipa protect` in playbooks | **Ready** | Can add to keylime-setup.yaml post-enrollment |
| PQ Tang ↔ akamu | **Available** | akamu already issues ML-KEM certs; kuipad uses same algorithms |
| vTPM binding | **Upstream planned** | Waiting on kuipa vTPM support; swtpm EK available today |
| Trust tier gating | **Arbiter ready** | Trust tier field in workload model; seal/unseal hooks needed |
| Termination cleanup | **EDA ready** | Add `kuipa cleanup` step to revocation playbook |

## Demo Talking Points

1. "Clone the VM — the identity stays behind" (kuipa protect + Keylime)
2. "Orchestrator can provision agents without seeing their credentials" (blind voucher)
3. "Post-quantum key wrapping protects agent data at rest today" (PQ Tang + akamu)
4. "Revocation is total — not just network isolation but credential destruction" (termination cleanup)
5. "Each defense layer is independently verifiable and mutually reinforcing" (full stack)
