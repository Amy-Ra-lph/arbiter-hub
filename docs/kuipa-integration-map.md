# kuipa ↔ Arbiter Hub Integration Map

kuipa is AB's Rust-based credential lifecycle tool for IPA-enrolled hosts.
Source: [github.com/abbra/kuipa](https://github.com/abbra/kuipa) (GPL-3.0, research prototype).
Created 2026-10-19, actively developed.

kuipa is **not an attestation backend** — it protects the *identity credentials*
that attestation backends verify against. It sits below Keylime/Arbiter Hub:

```
┌─────────────────────────────────────────────────┐
│  Arbiter Hub         Federation control plane   │
│  (state machine, policy, webhooks, EDA)         │
├─────────────────────────────────────────────────┤
│  Keylime / Falco     Platform verification      │
│  (TPM/IMA, eBPF syscall monitoring)             │
├─────────────────────────────────────────────────┤
│  kuipa               Credential lifecycle       │
│  (PQ enrollment, sealed keytab, PQ Tang)        │
├─────────────────────────────────────────────────┤
│  IPA + ahdapa        Identity governance        │
│  (Kerberos, HBAC, OAuth2, trust tiers)          │
└─────────────────────────────────────────────────┘
```

## What kuipa does

| Component | Crate | Function |
|---|---|---|
| **PQ enrollment** | `kuipa-enroll` | Host authenticates realm via pinned ML-DSA anchor, receives keytab + CA chain + realm config under ML-KEM. Auth methods: OTP, user password, existing TGT, blind voucher |
| **Sealed keytab** | `kuipa-tools` (`kuipa protect`) | Encrypts keytab at rest using PQ Tang bindings to each IPA server's escrow key. Keytab lives in tmpfs at runtime, unsealed at boot by `kuipa-unseal` |
| **PQ Tang** | `tang-pqc` / `tang-pqc-clevis` | ML-KEM-768 network-bound encryption. Works standalone for disk encryption (Clevis pin `tang-pqc`) or integrated into keytab sealing |
| **Blind voucher** | `ml-dsa-blind` + `kuipa-enroll` | Issuer signs blinded message — provisioner (orchestrator) never sees which host gets which credential. Single-use, bounded by host group + validity window |
| **Key rotation** | `kuipa-enroll` (rekey) | Forward-secrecy rotation of host keys without re-enrollment |
| **Secrets transport** | `kuipa-enroll` (§18) | Authenticated ML-KEM channel for moving secrets between servers (replaces ipa-custodia). Policy-gated by `cn=masters` membership |
| **User vaults** | `kuipa-tools` (`kuipa seal`) | User-space encrypted secret vaults with per-device factors (passphrase, PKCS#11 token, passkey planned). Recovery via PQ Tang commitment |
| **Trusted realms** | `kuipa-enroll` | Cross-realm trust anchors verified through Kerberos keys. Host can accept users from trusted realms with their KDCs and PKINIT anchors checked |
| **Server daemon** | `kuipad` | Runs behind httpd, talks to 389-ds via LDAPI. Serves enrollment, anchor exchange, Tang bindings, vault operations, secrets transport |

## Implementation Status (as of 2026-10-23)

| Feature | Status | Notes |
|---|---|---|
| PQ enrollment (OTP, password, TGT, voucher) | **Working** | Protocol library + client + server tested end-to-end |
| Anchor exchange + delegation | **Working** | Multi-server, succession chains |
| Sealed keytab (`kuipa protect/unseal`) | **Working** | PQ Tang bindings to IPA servers |
| PQ Tang service + Clevis pin | **Working** | ML-KEM-768 + ML-DSA-65 |
| Blind voucher enrollment | **Working** | `ml-dsa-blind` crate, quota enforcement |
| Secrets transport (§18) | **Working** | Keys operation, policy check, replica promotion scenario |
| Key rotation (rekey) | **Working** | Forward secrecy |
| Trusted realms | **Working** | Cross-realm anchor verification |
| User vaults (`kuipa seal`) | **Working** | Passphrase + PKCS#11 devices. Passkeys pending |
| gssproxy keytab holder | **Working** | Awaiting upstream gssproxy `keytab_loader` merge |
| TPM factor for sealed keytabs | **Designed, not built** | `kuipa prepare --tpm` planned (§7.1, §8.2) |
| Passkey device factor | **Designed, not built** | libfido2 FFI + ahdapa relying-party verifier |
| FreeIPA server integration | **Designed, not built** | Schema, ACIs, framework commands, installer changes |
| FreeIPA client integration | **Designed, not built** | `ipa-client-install --pq-enroll` |
| Real Clevis/LUKS2/dracut validation | **Pending** | `clevis luks bind` with `tang-pqc` pin |

## Feature Mapping to Arbiter Hub

| kuipa Feature | Arbiter Hub Integration Point | Status |
|---|---|---|
| **Blind voucher enrollment** | Workload onboarding (`POST /api/v1/workloads`). Voucher creates IPA host principal → Arbiter Hub auto-enrolls workload using that principal. Orchestrator (AAP) never sees the keytab | **Planned** — requires kuipa server-side on IPA host |
| **`kuipa protect`** (sealed keytab) | Complements Keylime TPM attestation. Keylime proves "OS unmodified"; kuipa proves "credential bound to this set of IPA servers". VM clone → keytab won't unseal → workload can't authenticate → distinct failure mode Arbiter Hub should detect | **Ready** — add `kuipa protect` to post-enrollment playbook |
| **PQ Tang (`tang-pqc`)** | Shares ML-KEM infrastructure with akamu PQC CA. Encrypted agent data stores. Disk encryption for bootc/Image Mode workloads | **Available** — akamu already issues ML-KEM certs |
| **vTPM/TPM binding** (planned) | When built: sealed keytab + Keylime become tightly coupled — same TPM proves both "host unmodified" (Keylime) and "credential belongs to this hardware" (kuipa) | **Upstream planned** — swtpm EK available today |
| **`kuipa seal`** (user vaults) | Trust tier gating. Sovereign-tier agents get kuipa-sealed credentials; lower tiers cannot unseal | **Arbiter ready** — trust tier field in workload model; seal/unseal hooks needed |
| **Secrets transport** | Replica promotion and CA key distribution via PQ-authenticated channel. Replaces ipa-custodia | **Working in kuipa** — FreeIPA adoption pending |
| **Termination cleanup** | Revocation chain: Arbiter Hub REVOKED → EDA playbook → `ipa host-disable` + `kuipa cleanup` → keytab + sealed vaults destroyed instantly | **EDA ready** — add `kuipa cleanup` step to revocation playbook |

## Security Narratives

### Snapshot Useless
VM clone → different server set (or TPM when built) → kuipa-protected keytab refuses to unseal.
Clone has no valid credential → cannot authenticate to anything → Keylime still shows the platform as healthy
but workload is effectively dead. Arbiter Hub should detect auth failures as a separate signal from attestation failures.

### Bounded Orchestrator Damage
Blind voucher: compromised orchestrator (AAP controller) cannot enumerate or steal agent identities.
Each agent enrolls via single-use voucher; orchestrator sees voucher handle but never the resulting keytab.
This is the anti-Storm-2372 property for machine identities.

### Post-Quantum from Day One
All enrollment, key wrapping, and Tang operations use ML-KEM-768 + ML-DSA-65 from OpenSSL 3.5.
No classical crypto in the critical path. FIPS 203/204 compliant. System crypto policy controls algorithm selection.

### Defense-in-Depth Stack

```
Layer 1: kuipa protect     — credential at rest (PQ-sealed keytab, bound to IPA servers)
Layer 2: Keylime           — platform integrity (continuous PCR/IMA verification)
Layer 3: Falco             — runtime behavior (eBPF syscall monitoring)
Layer 4: Arbiter Hub       — federation control plane (state machine, webhooks)
Layer 5: EDA               — automated response (quarantine/revoke/re-attest)
Layer 6: IPA + ahdapa      — identity governance (HBAC, OAuth2, DARC, trust tiers)
```

## Lifecycle Sequence

```
1. Agent VM boots
   └─ swtpm starts (TPM emulation)
   └─ Keylime agent registers with verifier

2. Workload onboarding
   └─ Arbiter Hub creates workload record (REGISTERED)
   └─ kuipa voucher enrollment → IPA host principal created
   └─ kuipa protect → keytab sealed to IPA server escrow keys
   └─ kuipa unseal at boot → keytab in tmpfs → Kerberos auth works

3. Attestation loop
   └─ Keylime verifier polls PCR + IMA continuously
   └─ Arbiter Hub polls verifier → HEALTHY state
   └─ Trust tier promotion: untrusted → verified → sovereign
   └─ Sovereign tier: kuipa seal unlocks additional secrets

4. Key rotation
   └─ kuipa rekey → new keys with forward secrecy
   └─ Re-seal keytab with new bindings
   └─ Arbiter Hub: workload remains HEALTHY (rotation is transparent)

5. Anomaly detected
   └─ Falco eBPF alert → Arbiter Hub webhook
   └─ State: HEALTHY → FAILED
   └─ EDA playbook: network fence + credential freeze

6. Revocation
   └─ Arbiter Hub: FAILED → REVOKED
   └─ EDA: ipa host-disable → PKINIT and sealed keytabs locked out
   └─ kuipa cleanup: keytab + sealed vaults destroyed
   └─ Keylime: agent removed from verifier

7. Re-attestation (if recoverable)
   └─ Fresh kuipa voucher → new keytab → re-seal
   └─ Keylime re-registers → Arbiter Hub: REGISTERED → ATTESTING → HEALTHY
```

## Potential New Attestation Signal: Credential Health

kuipa introduces a dimension that current Arbiter Hub backends don't cover:
**credential binding integrity**. The question isn't "is the OS unmodified?" (Keylime)
or "is the image signed?" (cosign) but "can this host actually unseal and use its identity?"

This could become a lightweight attestation signal:

```
kuipa check → {
  keytab_sealed: true,
  unseal_possible: true,       # PQ Tang binding to servers reachable
  servers_reachable: 2/3,      # how many IPA servers can serve recovery
  last_rekey: "2026-10-22",
  tpm_bound: false,            # future: TPM factor present
  vault_count: 3,
  vault_devices: ["passphrase", "pkcs11"]
}
```

Arbiter Hub could poll `kuipa check` as a lightweight "credential health" signal
alongside the heavier Keylime/Falco attestation — not a full backend, but a
readiness indicator. If `unseal_possible` drops to false (all IPA servers
unreachable or anchor rotated without rekey), the workload is about to lose
its identity even if the platform is still healthy.

## Demo Talking Points

1. "Clone the VM — the identity stays behind" (kuipa protect + PQ Tang)
2. "Orchestrator provisions agents without seeing their credentials" (blind voucher)
3. "Post-quantum key wrapping from enrollment through rest" (ML-KEM-768 everywhere)
4. "Revocation is total — not just network isolation but credential destruction" (kuipa cleanup)
5. "Key rotation happens without downtime or re-enrollment" (kuipa rekey)
6. "Each defense layer is independently verifiable and mutually reinforcing" (full stack)
7. "No changes to Kerberos or the KDC — pure client/server addition" (zero protocol changes)

## Differences from Prior Integration Map

This version updates the earlier integration map (written before kuipa source was available) with:

- Corrected architecture: kuipa uses PQ Tang bindings to IPA server escrow keys, not TPM PCR values (TPM factor is designed but not built)
- Added secrets transport (§18) — new since prior write-up
- Added user vaults (`kuipa seal`) — working with passphrase + PKCS#11 devices
- Added credential health signal concept
- Removed SUSPECT/QUARANTINED states (Arbiter Hub uses FAILED/UNDER_REMEDIATION)
- Updated all implementation statuses from kuipa source + TODO.md
