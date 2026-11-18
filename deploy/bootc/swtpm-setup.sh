#!/usr/bin/env bash
# swtpm initialization for Arbiter Hub IdM node (lab/demo only)
# Creates EK cert + platform cert for virtual TPM
set -euo pipefail

TPMSTATE="/var/lib/swtpm-localca"
STAMP="/var/lib/arbiter-hub/.swtpm-setup-complete"

[ -f "$STAMP" ] && { echo "swtpm already initialized"; exit 0; }

echo "Initializing swtpm state..."
mkdir -p "$TPMSTATE"

swtpm_setup \
    --tpmstate "$TPMSTATE" \
    --tpm2 \
    --createek \
    --create-ek-cert \
    --create-platform-cert \
    --lock-nvram

echo "Starting swtpm socket..."
# Socket mode for Keylime verifier/registrar on this host
exec swtpm socket \
    --tpmstate dir="$TPMSTATE" \
    --tpm2 \
    --ctrl type=tcp,port=2322 \
    --server type=tcp,port=2321 \
    --flags startup-clear
