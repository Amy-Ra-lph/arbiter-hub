#!/bin/bash
# Deploy Arbiter Hub partner cluster — KVM, bare-metal, or image-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/partner-common.sh"

SITE_ENV=""
TARGET="kvm"
DRY_RUN=false
OFFLINE=false
IMAGES_DIR=""
WORK_DIR=""

QUAY_REPO="quay.io/rhel-security/arbiter-bootc"
IMAGE_TAGS=(idm-identity arbiter-attestation arbiter-signing arbiter-agent)
ROLE_NAMES=(ipa hub signing agent)

for arg in "$@"; do
    case "$arg" in
        --site-env=*)   SITE_ENV="${arg#*=}" ;;
        --target=*)     TARGET="${arg#*=}" ;;
        --dry-run)      DRY_RUN=true ;;
        --offline)      OFFLINE=true ;;
        --images-dir=*) IMAGES_DIR="${arg#*=}"; OFFLINE=true ;;
        --work-dir=*)   WORK_DIR="${arg#*=}" ;;
        -h|--help)
            echo "Usage: deploy.sh --site-env=PATH [--target=kvm|bare-metal|image-only]"
            echo "                 [--dry-run] [--offline] [--images-dir=DIR] [--work-dir=DIR]"
            exit 0
            ;;
        *) log_err "Unknown arg: $arg"; exit 1 ;;
    esac
done

if [[ -z "$SITE_ENV" ]]; then
    log_err "Usage: deploy.sh --site-env=PATH [--target=kvm|bare-metal|image-only]"
    exit 1
fi

if [[ -z "$WORK_DIR" ]]; then
    WORK_DIR="$(mktemp -d)"
    log_info "Working directory: $WORK_DIR"
fi

CONFIGS_DIR="$WORK_DIR/configs"
CLOUD_INIT_DIR="$WORK_DIR/cloud-init"
mkdir -p "$CONFIGS_DIR" "$CLOUD_INIT_DIR"

# ── Generate per-node configs ──────────────────────────────────────
log_info "Generating per-node configs from $SITE_ENV"
"${SCRIPT_DIR}/generate-configs.sh" --site-env="$SITE_ENV" --output="$CONFIGS_DIR"

# shellcheck disable=SC1090
source "$SITE_ENV"

# ── Render cloud-init user-data from template + config ─────────────
render_cloud_init() {
    local role="$1" config_env="$2" fqdn="$3" output_path="$4"
    local template="${SCRIPT_DIR}/templates/cloud-init-${role}.yaml"

    if [[ ! -f "$template" ]]; then
        log_err "Template not found: $template"
        return 1
    fi

    local short_hostname="${fqdn%%.*}"
    local config_content
    config_content=$(cat "$config_env")
    local ssh_key="${SSH_PUBKEY:-}"

    # Indent config content for YAML (6 spaces for write_files content block)
    local indented_config
    indented_config=$(echo "$config_content" | sed 's/^/      /')

    sed \
        -e "s|__SHORT_HOSTNAME__|${short_hostname}|g" \
        -e "s|__FQDN__|${fqdn}|g" \
        -e "s|__SSH_PUBKEY__|${ssh_key}|g" \
        "$template" | \
    awk -v content="$config_content" '{
        if ($0 ~ /__CONFIG_ENV_CONTENT__/) {
            n = split(content, lines, "\n")
            for (i = 1; i <= n; i++) print "      " lines[i]
        } else {
            print
        }
    }' > "$output_path"
}

# ── Deploy a node via KVM ──────────────────────────────────────────
deploy_kvm_node() {
    local role="$1" config_env="$2" fqdn="$3" image_tag="$4"
    local userdata="$CLOUD_INIT_DIR/${fqdn%%.*}-user-data.yaml"

    # Also write role-named symlink for test convenience
    local role_userdata="$CLOUD_INIT_DIR/${role}-user-data.yaml"

    render_cloud_init "$role" "$config_env" "$fqdn" "$userdata"
    if [[ "$role" != "${fqdn%%.*}" ]]; then
        ln -sf "$(basename "$userdata")" "$role_userdata" 2>/dev/null || cp "$userdata" "$role_userdata"
    fi

    local image_source
    if $OFFLINE && [[ -n "$IMAGES_DIR" ]]; then
        image_source="${IMAGES_DIR}/${image_tag}.qcow2"
    else
        image_source="${QUAY_REPO}:${image_tag}"
    fi

    local vcpus=2 ram=4096 disk=20
    case "$role" in
        ipa)     ram=8192; disk=40 ;;
        hub)     ram=4096; disk=20 ;;
        signing) ram=4096; disk=20 ;;
        agent)   ram=2048; disk=20; vcpus=1 ;;
    esac

    local cmd="virt-install --name ${fqdn%%.*} --memory ${ram} --vcpus ${vcpus}"
    cmd+=" --disk size=${disk},format=qcow2"
    cmd+=" --cloud-init user-data=${userdata}"
    cmd+=" --os-variant fedora44"
    cmd+=" --network bridge=virbr0"
    cmd+=" --graphics none --noautoconsole"

    if $OFFLINE && [[ -n "$IMAGES_DIR" ]]; then
        cmd+=" --disk ${image_source},device=disk,bus=virtio"
    else
        cmd+=" --location ${image_source}"
    fi

    if $DRY_RUN; then
        echo "[DRY-RUN] $cmd"
    else
        log_info "Deploying ${role} node: ${fqdn}"
        eval "$cmd"
        wait_for_node "$fqdn"
    fi
}

# ── Wait for a node to finish firstboot ────────────────────────────
wait_for_node() {
    local fqdn="$1"
    local stamp="/var/lib/idm-image-mode/.firstboot-complete"
    [[ "$1" != *"ipa"* ]] && stamp="/var/lib/arbiter-hub/.firstboot-complete"

    log_info "Waiting for $fqdn to become reachable..."
    for i in $(seq 1 60); do
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${fqdn}" \
            "test -f $stamp" 2>/dev/null; then
            log_ok "$fqdn firstboot complete"
            return 0
        fi
        sleep 10
    done
    log_err "$fqdn did not complete firstboot within 10 minutes"
    return 1
}

# ── Main deploy flow ───────────────────────────────────────────────
log_info "Deploying Arbiter Hub cluster — target: ${TARGET}"

case "$TARGET" in
    kvm)
        deploy_kvm_node "ipa" "$CONFIGS_DIR/ipa-config.env" \
            "$IPA_HOSTNAME" "idm-identity"

        deploy_kvm_node "hub" "$CONFIGS_DIR/hub-config.env" \
            "$HUB_HOSTNAME" "arbiter-attestation"

        deploy_kvm_node "signing" "$CONFIGS_DIR/signing-config.env" \
            "$SIGNING_HOSTNAME" "arbiter-signing"

        read -ra AGENTS <<< "${AGENT_HOSTNAMES}"
        for agent_host in "${AGENTS[@]}"; do
            local_config="$CONFIGS_DIR/agent-${agent_host}-config.env"
            [[ ! -f "$local_config" ]] && local_config="$CONFIGS_DIR/agent-config.env"
            deploy_kvm_node "agent" "$local_config" \
                "$agent_host" "arbiter-agent"
        done
        ;;

    bare-metal|image-only)
        log_err "Target '${TARGET}' not yet implemented — see Task 3"
        exit 1
        ;;

    *)
        log_err "Unknown target: ${TARGET} (expected: kvm, bare-metal, image-only)"
        exit 1
        ;;
esac

if ! $DRY_RUN; then
    log_ok "Cluster deployed:"
    echo "  IPA:     ${IPA_HOSTNAME}"
    echo "  Hub:     ${HUB_HOSTNAME}"
    echo "  Signing: ${SIGNING_HOSTNAME}"
    echo "  Agents:  ${AGENT_HOSTNAMES}"
fi
