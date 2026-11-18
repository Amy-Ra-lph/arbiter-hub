# Persona Demo Flows — Design

## Intent

Build four demo experiences from the same 3-node lab, each telling a
different story to a different audience. The infrastructure is identical;
the narrative, pacing, and emphasis change per persona.

### Why now

Arbiter Hub has 10 healthy workloads, OIDC auth, Keylime attestation,
Falco monitoring, enforcement-mcp policy, 3 trust tiers, and 5 demo
personas. kuipa signing adds artifact provenance. The platform is
demo-ready; what's missing is the storytelling layer that maps it to
audience-specific value propositions.

### What success looks like

Each demo can be run independently in under 15 minutes, from the same
lab, by the same person, with no setup between runs. An audience member
walks away with a clear, memorable understanding of the value — not a
feature list.

## Audiences and Core Messages

### 1. Internal Executive

**Audience:** RH VPs, SVPs, BU leads (especially those who equate
"AI platform" with OCP).

**Core message:** AI agents run on RHEL everywhere — VMs, edge, cloud,
bare metal. The trust and identity layer (IdM + attestation + signing)
is platform infrastructure below the orchestrator. It makes the entire
RH portfolio more valuable:

- **RHEL+IdM** = trust foundation (attestation, identity, signing, policy)
- **AAP** = automated response (EDA rulebooks trigger on attestation
  events, AWX runs remediation playbooks)
- **OCP** = container orchestration, extending the same trust model via
  SPIRE and workload identity federation

This isn't three products competing — it's one security pipeline that
spans the portfolio. RHEL Security/IdM enables upsell to AAP (for the
automation) and OCP (for the orchestration), because the trust
foundation is already there.

**Misconception to break:** "AI = OCP." The demo runs on 3 bare RHEL
VMs. No OpenShift. Full pipeline works. That's the point.

**Anti-goal:** Do not position RHEL Security as a competitor to OCP
security. Position it as the layer underneath that makes OCP security
(and AAP automation) more valuable.

**Demo flow (exec-demo.sh):**

1. **The estate** — Show 10 workloads across 3 trust tiers, all healthy.
   "This is a fleet of AI agents, managed by identity, attested by
   hardware, monitored by runtime policy. No OpenShift."
2. **Identity is the control plane** — Enroll a new agent. IPA principal
   → OIDC token → Arbiter Hub registration → Keylime attestation → healthy.
   "Identity Management is the single control plane for agent trust."
3. **Automated response (AAP story)** — Trigger rogue agent in
   wid-untrusted. Falco detects → EDA rulebook fires → remediation
   playbook runs → workload revoked. "This is where AAP plugs in —
   Ansible automation responds to attestation events."
4. **Container readiness (OCP story)** — Show cosign-verified bootc
   workload. "When this workload moves to OCP, the attestation follows.
   Same trust model, same identity, orchestrated at scale."
5. **PQ-ready supply chain (differentiation)** — kuipa sign an artifact.
   ML-DSA-65 signature, transparency log entry. "Post-quantum signing
   with no external PKI. Identity-native. Industry first."
6. **Portfolio map** — Summary slide: RHEL (trust) + AAP (response) +
   OCP (orchestrate) = portfolio multiplier. Each upsell adds value
   because the foundation is already there.

**Estimated time:** 12 min.

### 2. Developer

**Audience:** Customer developers building AI agents / agentic
applications.

**Core message:** Security is invisible when you're clean, actionable
when you're not. You deploy, you get attested, you sign your artifacts.
If something's wrong, you see exactly what to fix.

**Anti-goal:** Do not make the developer feel surveilled. The framing is
"we help you ship safely," not "we watch everything you do."

**Demo flow (dev-demo.sh):**

1. **Developer pushes agent code** — Carol (pipeline persona) pushes a
   bootc image. "As a developer, you push your code. That's it."
2. **Prescan** — enforcement-mcp scans the image against policy (SELinux
   context, fapolicyd rules, AIDE baseline). Two findings:
   - `container_connect_any` SELinux boolean enabled (should be off)
   - Missing fapolicyd allow rule for agent binary
3. **Findings report** — HTML report opens in browser. Clean layout:
   finding, severity, specific fix command. Not a wall of CVEs — two
   actionable items with copy-paste remediation.
4. **Remediate** — Developer applies fixes (shown as commands).
   Re-scan: clean.
5. **Auto-enrollment** — Clean image → CI enrollment endpoint →
   Arbiter Hub registers → Keylime enrolls (skip-if-healthy) → attests
   → **HEALTHY**.
6. **Sign** — `kuipa sign blob release-1.0.tar` — artifact signed with
   developer's Kerberos identity. Transparency log entry shows who,
   what, when. "Your code has provenance. No GPG key management."
7. **Verify** — `kuipa sign verify` — offline verification. "Anyone
   with the realm anchor can verify this. No server needed."

**Estimated time:** 10 min.

### 3. CISO

**Audience:** Customer CISOs and security leadership evaluating AI
risk.

**Core message:** You're throttling AI adoption because you can't prove
trust. We give you the proof — hardware-rooted attestation, policy
enforcement, audit trails, automated remediation — so you can open the
throttle. Risk reduction enables value realization.

**Anti-goal:** Do not present a feature matrix. The CISO cares about
outcomes: "can I prove compliance?", "what happens when an agent goes
rogue?", "do I have an audit trail?"

**Demo flow (ciso-demo.sh):**

1. **Fleet visibility** — Dashboard: 10 workloads, 3 trust tiers
   (sovereign/verified/untrusted), real-time attestation status. "You
   can see every agent and its trust level."
2. **Trust tier model** — Explain: sovereign = full access,
   verified = limited, untrusted = sandboxed + monitored. Policy
   gates what each tier can do. "Risk is graduated, not binary."
3. **Compliance evidence** — Show attestation records: hardware quote,
   timestamp, policy hash, verdict. "This is auditable proof that host
   X was compliant at time Y."
4. **Incident response** — Launch rogue agent in untrusted sandbox.
   Falco detects sensitive file access → behavioral classifier flags
   injection attempt → EDA triggers quarantine → workload state moves
   to FAILED → admin revokes. "Detection to containment: automated.
   Full audit trail."
5. **Audit trail** — Show audit log: every state transition, every
   actor, every timestamp. "This is your evidence chain for regulators."
6. **Provenance** — kuipa transparency log. "Every artifact signed,
   every signing event logged. Post-quantum. Non-repudiable."
7. **Investment enablement** — "The more you trust the pipeline, the
   more agents you deploy. This isn't a brake — it's what lets you
   accelerate."

**Estimated time:** 12 min.

### 4. RSAC (Industry)

**Audience:** Security professionals, analysts, press at RSA
Conference.

**Core message:** The industry is building AI agents without a trust
model. Here's one: hardware-rooted attestation + identity-native
signing + realm-policy-gated trust tiers + post-quantum crypto. Open
standards, composable, no vendor lock-in.

**Anti-goal:** Do not make this a product pitch. RSAC wants thought
leadership. The product backs up the thesis, it doesn't lead.

**Demo flow (rsac-demo.sh):**

1. **The problem** — "Every AI agent runs with implicit trust. There's
   no hardware root of trust, no identity lifecycle, no audit trail.
   The industry is building the 2027 version of 'just run as root.'"
2. **The model** — Architecture diagram: identity (IPA/Kerberos) →
   attestation (Keylime/TPM) → policy (enforcement-mcp) → monitoring
   (Falco) → signing (kuipa/ML-DSA) → remediation (EDA). "Six layers,
   open standards at each."
3. **Live: enrollment to attestation** — New workload → IPA principal →
   OIDC token → Keylime quote → PASS. "Hardware-rooted trust in 30
   seconds."
4. **Live: the hard thing** — Attested signing. `kuipa sign` with
   Kerberos ticket → server validates → transparency log entry →
   ML-DSA-65 signature. Offline verify. "Identity-native signing, no
   external CA, post-quantum. sigstore model but with Kerberos realm
   authority."
5. **Live: rogue agent containment** — Fast version: trigger → detect →
   quarantine → revoke. 60 seconds. "Automated trust revocation."
6. **Standards alignment** — WIMSE, AuthZEN, NIST AI 100-2, EU AI Act.
   "This maps to where regulation is going."
7. **Open invitation** — "The components are open. The architecture is
   composable. We're contributing to the standards. What's your trust
   model?"

**Estimated time:** 15 min (with audience interaction).

## Infrastructure to Build

### A. Developer IDE + Prescan Container

**What:** A container on the agent node that runs enforcement-mcp scans
against a workload image and produces an HTML findings report.

**Components:**
- `prescan-runner.sh` — script that invokes enforcement-mcp tools
  (selinux_check_context, fapolicyd_list_rules, aide_check) against a
  target container/image
- `prescan-report.html.j2` — Jinja2 template for the HTML findings
  report. Clean, branded, two-column: finding + fix.
- `prescan-remediate.sh` — applies the fixes shown in the report, then
  re-runs the scan to confirm clean.
- Demo "bad image" with intentional policy violations for the scan to
  find.

**Not building:** Full code-server/VS Code. Terminal walkthrough +
HTML report is the IDE stand-in.

### B. kuipa Signing Integration

**What:** Wire kuipa signing into the Arbiter Hub demo flow so
attestation and signing are shown as one pipeline.

**Components:**
- kuipa is not installed on the lab yet. Needs: kuipa binary on agent
  node, kuipad on idm node, enrollment of agent host.
- `signing-demo.sh` — script that runs `kuipa sign` and `kuipa sign
  verify`, formats output for demo.
- If kuipa install is blocked (AB still iterating on macOS, lab runs
  RHEL): simulate with a mock-kuipa script that produces the same
  formatted output. Flag clearly as simulated in the script.

**Decision: kuipa IS installable on RHEL 10.** Lab has OpenSSL 3.5.9
(meets ≥3.5 requirement). Only blocker: Rust 1.89+ needed (RHEL 10
ships 1.84 in AppStream). Fix: `rustup default 1.89.0`. Build deps
standard (`openssl-devel krb5-devel openldap-devel libfido2-devel
clang-devel`). All crypto from OpenSSL via `native-ossl` — no vendored
crypto, FIPS-friendly. Ansible roles for server (`kuipa_server`) and
client (`kuipa_client`) already exist in `deploy/ansible/roles/`.
AB's PDF confirms `kuipa sign blob` and `kuipa sign verify` = "works"
(156/156 playground steps pass, 18 use cases, 14 working).

**Plan:** Build from source on idm node (kuipad) and agent node
(kuipa + kuipa-unseal) using existing ansible roles. No mock needed.
Fallback if cargo build fails: mock sign/verify output only.

### C. Persona Demo Scripts

**What:** Four shell scripts, one per audience, following the flows
above. All domain-agnostic (pick up from `ARBITER_*` env vars like
`onboarding.sh`).

**Files:**
- `demo/scenarios/exec-demo.sh`
- `demo/scenarios/dev-demo.sh`
- `demo/scenarios/ciso-demo.sh`
- `demo/scenarios/rsac-demo.sh`

Each script:
- Sources a shared `demo/scenarios/lib/demo-lib.sh` (banner, step, ok,
  warn, fail, pause, get_token, api_call functions — extracted from
  existing scripts).
- Uses `DEMO_PAUSE` for timing control.
- Has `--auto` flag for unattended run (replaces pause with sleep).
- Cleans up any workloads it creates at the end.
- Prints a summary with key talking points for the presenter.

### D. Shared Assets

- `demo/scenarios/lib/demo-lib.sh` — shared functions
- `demo/scenarios/lib/talking-points.sh` — per-persona bullet points
  printed before each act, so the presenter knows what to say
- `demo/scenarios/env/rebuild.env` — env vars for the rebuild lab
- `demo/scenarios/env/arbiter.env.template` — template for other labs

## Constraints

- All demos run from the hub or idm node via SSH. No local tooling
  requirements beyond a terminal.
- No OpenShift dependency anywhere. This is deliberate and
  load-bearing for the exec story.
- Scripts must be idempotent — safe to run multiple times without
  accumulating stale workloads.
- kuipa builds from source on RHEL 10 (confirmed). If cargo build
  fails as edge case, fall back to mock for sign/verify output only.
- HTML report served via `python3 -m http.server` on the hub node,
  not a persistent web server.
- enforcement-mcp tools called via HTTP JSON-RPC to port 8402 on hub
  node (same pattern as existing `mcp-access-matrix.sh`).
- Falco is live on agent node and detects real events. EDA/AWX
  quarantine is narrated — scripts call Hub API to transition workload
  state, then show audit trail and explain where EDA plugs in.
- "Bad image" for prescan: create Containerfile with intentional
  violations (`container_connect_any` boolean, missing fapolicyd rule).
  Push to local registry at 10.89.0.186:5000.

## Non-goals

- Workshop/hands-on lab guide (that's a separate deliverable)
- Video recording (use `/screen-record` separately)
- Slide deck (use `/presentation-toolkit` separately)
- OCP integration demo (future, after trust model proven on RHEL)
- Real EDA/AWX attestation rulebooks (narrated in demo, future work)

## Calls I Made

- **Terminal over code-server** for the developer IDE experience.
  Reliability and narrative control win for presentation demos.
- **HTML report** for prescan findings instead of terminal-only output.
  Gives a "portal" feel without infrastructure.
- **Shared demo-lib.sh** extracted from existing scripts rather than
  duplicating banner/step/ok functions in each script.
- **Real kuipa, not mock** — confirmed buildable on RHEL 10 with rustup.
  Ansible roles exist. No reason to mock.
- **No OCP in any demo** — the absence is the message for execs.
- **EDA narrated, not wired** — AWX+EDA pipeline verified E2E
  separately but no attestation-specific rulebooks exist. Scripts
  show audit trail and explain integration point.
- **enforcement-mcp via HTTP** — JSON-RPC to hub:8402, same as
  mcp-access-matrix.sh. Prescan runs from hub or agent node with
  network access to enforcement-mcp server.
