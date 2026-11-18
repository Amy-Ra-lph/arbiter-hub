#!/usr/bin/env bash
# Seal Arbiter Hub application secrets for a production firstboot.
#
# Run once on the deployed system, as root, BEFORE arbiter-server-firstboot
# runs. Produces /etc/arbiter/secrets/<name>.cred sealed with systemd-creds.
# Plaintext is written only to a temporary file and removed after a verified
# round-trip; firstboot decrypts the sealed value at provisioning time.
set -euo pipefail
umask 077

SECRETS_DIR="${SECRETS_DIR:-/etc/arbiter/secrets}"
# name:bytes
SECRET_SPECS=("db_password:32" "local_admin_password:24")

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run as root" >&2
    exit 1
fi
if ! command -v systemd-creds >/dev/null 2>&1; then
    echo "ERROR: systemd-creds not found (systemd package missing?)" >&2
    exit 1
fi

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

for spec in "${SECRET_SPECS[@]}"; do
    name="${spec%%:*}"
    bytes="${spec##*:}"
    cred="${SECRETS_DIR}/${name}.cred"

    if [ -e "$cred" ]; then
        echo "exists, leaving untouched: ${cred}"
        continue
    fi
    if [ -e "${SECRETS_DIR}/${name}" ]; then
        echo "WARNING: plaintext ${SECRETS_DIR}/${name} exists and will be used as the source" >&2
    fi

    tmp="$(mktemp)"
    if [ -e "${SECRETS_DIR}/${name}" ]; then
        cp "${SECRETS_DIR}/${name}" "$tmp"
        chmod 600 "$tmp"
    else
        openssl rand -base64 "$bytes" > "$tmp"
    fi

    systemd-creds encrypt --name="$name" --with-key=host+tpm2 "$tmp" "$cred"
    chmod 600 "$cred"

    if ! systemd-creds decrypt --name="$name" --with-key=host+tpm2 "$cred" - | cmp -s - "$tmp"; then
        echo "ERROR: round-trip verification failed for ${name}" >&2
        rm -f "$tmp"
        exit 1
    fi
    rm -f "$tmp"
    echo "sealed: ${cred}"
done

echo "Sealing complete. Firstboot decrypts these into ${SECRETS_DIR}/<name> at provisioning time."
