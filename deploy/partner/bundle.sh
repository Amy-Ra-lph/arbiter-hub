#!/bin/bash
# Create air-gapped bundle for partner delivery via USB/file transfer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/partner-common.sh"

DRY_RUN=false
OUTPUT_DIR="."
QUAY_REPO="quay.io/rhel-security/arbiter-bootc"
IMAGE_TAGS=(idm-identity arbiter-attestation arbiter-signing arbiter-agent)
DATE=$(date +%Y-%m-%d)
BUNDLE_NAME="arbiter-hub-partner-bundle-${DATE}"

for arg in "$@"; do
    case "$arg" in
        --dry-run)      DRY_RUN=true ;;
        --output=*)     OUTPUT_DIR="${arg#*=}" ;;
        -h|--help)
            echo "Usage: bundle.sh [--dry-run] [--output=DIR]"
            echo "Creates air-gapped bundle with bootc images + deploy scripts."
            exit 0
            ;;
        *) log_err "Unknown arg: $arg"; exit 1 ;;
    esac
done

STAGING_DIR=$(mktemp -d)
trap 'rm -rf "$STAGING_DIR"' EXIT

BUNDLE_DIR="$STAGING_DIR/$BUNDLE_NAME"
IMAGES_DIR="$BUNDLE_DIR/images"
SCRIPTS_DIR="$BUNDLE_DIR/deploy"
mkdir -p "$IMAGES_DIR" "$SCRIPTS_DIR"

log_info "Preparing bundle: $BUNDLE_NAME"

# ── Pull and save container images ─────────────────────────────────
total_size=0
for tag in "${IMAGE_TAGS[@]}"; do
    image="${QUAY_REPO}:${tag}"
    archive="${IMAGES_DIR}/${tag}.tar"

    if $DRY_RUN; then
        echo "[DRY-RUN] podman pull ${image}"
        echo "[DRY-RUN] podman save -o ${archive} ${image}"
        # Estimate ~1.5 GB per bootc image
        total_size=$((total_size + 1500))
    else
        log_info "Pulling: ${image}"
        podman pull "${image}"
        log_info "Saving: ${archive}"
        podman save -o "${archive}" "${image}"
        size_mb=$(du -m "${archive}" | cut -f1)
        total_size=$((total_size + size_mb))
        log_ok "Saved ${tag} (${size_mb} MB)"
    fi
done

# ── Copy deploy scripts ───────────────────────────────────────────
if $DRY_RUN; then
    echo "[DRY-RUN] Copy deploy/partner/ → bundle"
else
    cp -r "${SCRIPT_DIR}"/{*.sh,*.example,lib,templates} "$SCRIPTS_DIR/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}/integrations" "$SCRIPTS_DIR/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}/docs" "$SCRIPTS_DIR/" 2>/dev/null || true
fi

# ── Write bundle README ───────────────────────────────────────────
cat > "$BUNDLE_DIR/README.md" <<'READMEEOF'
# Arbiter Hub Partner Bundle — Offline Deployment

This bundle contains everything needed to deploy the Arbiter Hub stack
without internet access.

## Contents

- `images/` — bootc container images (OCI archives)
  - `idm-identity.tar` — IPA Primary (FreeIPA + ahdapa + akamu)
  - `arbiter-attestation.tar` — Hub (API + UI + MCP + Keylime + Trustee)
  - `arbiter-signing.tar` — Signing (cosign + Rekor + registry)
  - `arbiter-agent.tar` — Agent (arbiter-agent + keylime_agent)
- `deploy/` — deployment scripts, templates, and examples

## Quick Start

```bash
# 1. Copy site.env template and fill in your values
cp deploy/site.env.example site.env
$EDITOR site.env

# 2. Load images into local container storage
for img in images/*.tar; do
    podman load -i "$img"
done

# 3. Deploy (KVM example)
./deploy/deploy.sh --site-env=site.env --target=kvm --offline --images-dir=images/

# 4. Verify
./deploy/verify-deployment.sh --site-env=site.env
```

## Image Loading for KVM

For KVM deployment, convert OCI images to qcow2 disk images:
```bash
for img in images/*.tar; do
    name=$(basename "$img" .tar)
    podman load -i "$img"
    # Use bootc to create disk image, or deploy via cloud-init
done
```

## Notes

- All images are Fedora 44 bootc (ostree-based, immutable /usr)
- PQC support requires RHCS root CA with ML-DSA enabled (not included)
- See deploy/site.env.example for all configuration options
READMEEOF

# ── Create tarball ─────────────────────────────────────────────────
if $DRY_RUN; then
    echo ""
    echo "=== Bundle contents ==="
    echo "  Images: ${#IMAGE_TAGS[@]} bootc images (~${total_size} MB total)"
    for tag in "${IMAGE_TAGS[@]}"; do
        echo "    - ${tag}"
    done
    echo "  Scripts: deploy/, lib/, templates/"
    echo "  Docs: README.md"
    echo "  Bundle: ${OUTPUT_DIR}/${BUNDLE_NAME}.tar.gz"
    echo "  Estimated size: ~$((total_size + 10)) MB"
else
    TARBALL="${OUTPUT_DIR}/${BUNDLE_NAME}.tar.gz"
    log_info "Creating bundle: ${TARBALL}"
    tar -czf "${TARBALL}" -C "$STAGING_DIR" "$BUNDLE_NAME"
    final_size=$(du -m "${TARBALL}" | cut -f1)
    log_ok "Bundle created: ${TARBALL} (${final_size} MB)"
fi
