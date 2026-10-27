#!/usr/bin/env bash
# Per-persona talking points — printed before each act

exec_points() {
    local act="$1"
    case "$act" in
        1) talking_point "This is a fleet of AI agents — managed by identity, attested by hardware, monitored by policy. No OpenShift." ;;
        2) talking_point "Identity Management is the single control plane for agent trust." ;;
        3) talking_point "This is where AAP plugs in — Ansible automation responds to attestation events." ;;
        4) talking_point "When this workload moves to OCP, the attestation follows. Same trust model, same identity." ;;
        5) talking_point "Post-quantum signing with no external PKI. Identity-native. Industry first." ;;
        6) talking_point "RHEL (trust) + AAP (response) + OCP (orchestrate) = portfolio multiplier." ;;
    esac
}

dev_points() {
    local act="$1"
    case "$act" in
        1) talking_point "As a developer, you push your code. That's it." ;;
        2) talking_point "Two actionable findings with copy-paste remediation. Not a wall of CVEs." ;;
        3) talking_point "Clean scan, clean image, auto-enrolled. Security is invisible when you're clean." ;;
        4) talking_point "Your code has provenance. No GPG key management." ;;
        5) talking_point "Anyone with the realm anchor can verify this. No server needed." ;;
    esac
}

ciso_points() {
    local act="$1"
    case "$act" in
        1) talking_point "You can see every agent and its trust level. Risk is graduated, not binary." ;;
        2) talking_point "Auditable proof that host X was compliant at time Y." ;;
        3) talking_point "Detection to containment: automated. Full audit trail." ;;
        4) talking_point "Every artifact signed, every event logged. Post-quantum. Non-repudiable." ;;
        5) talking_point "This isn't a brake — it's what lets you accelerate AI adoption." ;;
    esac
}

rsac_points() {
    local act="$1"
    case "$act" in
        1) talking_point "The industry is building the 2027 version of 'just run as root.'" ;;
        2) talking_point "Six layers, open standards at each." ;;
        3) talking_point "Hardware-rooted trust in 30 seconds." ;;
        4) talking_point "Identity-native signing. sigstore model but with Kerberos realm authority." ;;
        5) talking_point "Automated trust revocation." ;;
        6) talking_point "The components are open. The architecture is composable. What's your trust model?" ;;
    esac
}
