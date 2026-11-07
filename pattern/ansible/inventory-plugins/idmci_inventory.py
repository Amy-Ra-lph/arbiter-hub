"""
AAP Dynamic Inventory Plugin: IdM-CI Provisioned Hosts

Reads IdM-CI metadata YAML and Beaker job API to build an Ansible
inventory with groups matching the Arbiter Hub topology:

  ipaserver      — IPA primary (idm node)
  ipaclient      — IPA clients (hub + agent nodes)
  arbiter_hub    — Attestation hub (containers, EDA)
  arbiter_agent  — Agent runtime (Keylime, Falco, OpenShell)

Configuration (idmci_inventory.yaml):
  plugin: idmci_inventory
  metadata_file: idm-ci/metadata-arbiter-demo-3node.yaml  # or URL
  beaker_job_id: "J:1200306184"  # optional — overrides metadata with live IPs
  ssh_key_file: ~/.ssh/idm_ci_key
  ssh_user: root

Install in AAP:
  1. Place in project repo: pattern/ansible/inventory-plugins/
  2. In AAP: Settings → Inventory → Custom Inventory Source
  3. Source: "Sourced from a Project", select this file
  4. Or: create inventory source pointing to this script

Requires: python3-pyyaml, python3-requests (for Beaker API)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DOCUMENTATION = r"""
    name: idmci_inventory
    plugin_type: inventory
    short_description: IdM-CI / Beaker dynamic inventory for Arbiter Hub
    description:
        - Reads IdM-CI metadata YAML to discover host topology
        - Optionally queries Beaker API for live provisioned IPs
        - Creates groups matching arbiter-hub inventory structure
    options:
        metadata_file:
            description: Path or URL to IdM-CI metadata YAML
            required: true
            type: str
        beaker_job_id:
            description: Beaker job ID (J:NNNN) for live IP lookup
            required: false
            type: str
        ssh_key_file:
            description: SSH private key path
            default: ~/.ssh/idm_ci_key
            type: str
        ssh_user:
            description: SSH username
            default: root
            type: str
        domain:
            description: Override domain from metadata
            required: false
            type: str
"""

try:
    from ansible.plugins.inventory import BaseInventoryPlugin
    HAS_ANSIBLE = True
except ImportError:
    HAS_ANSIBLE = False

try:
    import yaml
except ImportError:
    yaml = None

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


BEAKER_API_BASE = "https://beaker.engineering.redhat.com"

# Role → inventory group mapping
ROLE_GROUP_MAP = {
    "master": "ipaserver",
    "client": "ipaclient",
}

# Host prefix → additional group mapping
HOST_GROUP_MAP = {
    "hub": "arbiter_hub",
    "agent": "arbiter_agent",
    "idm": "ipaserver",
}


def _parse_metadata(metadata_path: str) -> dict:
    """Parse IdM-CI metadata YAML and extract host topology."""
    if yaml is None:
        raise RuntimeError("PyYAML required: pip install pyyaml")

    path = Path(os.path.expanduser(metadata_path))
    if not path.exists():
        raise FileNotFoundError(f"Metadata not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    return data


def _beaker_job_hosts(job_id: str) -> dict[str, str]:
    """Query Beaker API for provisioned hostnames and IPs.

    Returns: {fqdn_from_metadata: beaker_fqdn}
    """
    if not HAS_REQUESTS:
        return {}

    job_num = job_id.replace("J:", "")
    url = f"{BEAKER_API_BASE}/jobs/{job_num}"
    headers = {"Accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, timeout=30,
                            verify=True, auth=None)
        resp.raise_for_status()
    except Exception:
        # Fall back to metadata-only if Beaker unreachable
        return {}

    data = resp.json()
    hosts = {}

    for recipe_set in data.get("recipe_sets", []):
        for recipe in recipe_set.get("recipes", []):
            fqdn = recipe.get("system", {}).get("fqdn", "")
            # Map by recipe role annotation or positional order
            role = recipe.get("role", "")
            if fqdn:
                hosts[role] = fqdn

    return hosts


def _resolve_host_ip(fqdn: str) -> str | None:
    """Resolve FQDN to IP via DNS. Returns None on failure."""
    import socket
    try:
        return socket.gethostbyname(fqdn)
    except socket.gaierror:
        return None


def build_inventory(
    metadata_path: str,
    beaker_job_id: str | None = None,
    ssh_key_file: str = "~/.ssh/idm_ci_key",
    ssh_user: str = "root",
    domain_override: str | None = None,
) -> dict:
    """Build inventory dict from IdM-CI metadata + optional Beaker lookup."""
    data = _parse_metadata(metadata_path)

    # Extract domain and hosts from metadata
    domain_cfg = data.get("domains", [{}])[0]
    domain = domain_override or domain_cfg.get("name", "arbiter.demo")
    hosts_cfg = domain_cfg.get("hosts", [])

    # Optional: get live Beaker FQDNs
    beaker_hosts = {}
    if beaker_job_id:
        beaker_hosts = _beaker_job_hosts(beaker_job_id)

    inventory = {
        "_meta": {"hostvars": {}},
        "all": {
            "vars": {
                "ansible_user": ssh_user,
                "ansible_ssh_private_key_file": os.path.expanduser(ssh_key_file),
                "ansible_ssh_common_args": (
                    "-o StrictHostKeyChecking=no "
                    "-o UserKnownHostsFile=/dev/null"
                ),
                "global_domain": domain,
            },
            "children": ["ipaserver", "ipaclient", "arbiter_hub", "arbiter_agent"],
        },
        "ipaserver": {"hosts": [], "vars": {}},
        "ipaclient": {"hosts": [], "vars": {}},
        "arbiter_hub": {"hosts": [], "vars": {}},
        "arbiter_agent": {"hosts": [], "vars": {}},
    }

    for host_cfg in hosts_cfg:
        meta_fqdn = host_cfg["name"]  # e.g. idm.arbiter.demo
        role = host_cfg.get("role", "client")
        prefix = meta_fqdn.split(".")[0]  # idm, hub, agent

        # Use Beaker FQDN if available, else metadata FQDN
        actual_fqdn = beaker_hosts.get(role, meta_fqdn)

        # Resolve IP
        ip = _resolve_host_ip(actual_fqdn)

        # Host vars
        hostvars = {
            "ansible_host": ip or actual_fqdn,
            "ansible_fqdn": actual_fqdn,
            "meta_fqdn": meta_fqdn,
            "host_role": role,
            "host_prefix": prefix,
            "os": host_cfg.get("os", "fedora-44"),
        }

        # Add to role-based group
        role_group = ROLE_GROUP_MAP.get(role, "ipaclient")
        if meta_fqdn not in inventory[role_group]["hosts"]:
            inventory[role_group]["hosts"].append(meta_fqdn)

        # Add to topology-based group
        topo_group = HOST_GROUP_MAP.get(prefix)
        if topo_group and topo_group != role_group:
            if meta_fqdn not in inventory[topo_group]["hosts"]:
                inventory[topo_group]["hosts"].append(meta_fqdn)

        inventory["_meta"]["hostvars"][meta_fqdn] = hostvars

    return inventory


if HAS_ANSIBLE:
    class InventoryModule(BaseInventoryPlugin):
        NAME = "idmci_inventory"

        def verify_file(self, path: str) -> bool:
            return path.endswith(("idmci_inventory.yaml", "idmci_inventory.yml"))

        def parse(self, inventory, loader, path, cache=True):
            super().parse(inventory, loader, path, cache)
            self._read_config_data(path)

            metadata_file = self.get_option("metadata_file")
            beaker_job_id = self.get_option("beaker_job_id")
            ssh_key_file = self.get_option("ssh_key_file")
            ssh_user = self.get_option("ssh_user")
            domain = self.get_option("domain")

            inv = build_inventory(
                metadata_path=metadata_file,
                beaker_job_id=beaker_job_id,
                ssh_key_file=ssh_key_file,
                ssh_user=ssh_user,
                domain_override=domain,
            )

            # Populate ansible inventory object
            for group_name in ["ipaserver", "ipaclient", "arbiter_hub", "arbiter_agent"]:
                self.inventory.add_group(group_name)
                group_data = inv.get(group_name, {})
                for var_name, var_val in group_data.get("vars", {}).items():
                    self.inventory.set_variable(group_name, var_name, var_val)

            all_vars = inv.get("all", {}).get("vars", {})
            for var_name, var_val in all_vars.items():
                self.inventory.set_variable("all", var_name, var_val)

            hostvars = inv.get("_meta", {}).get("hostvars", {})
            for hostname, hvars in hostvars.items():
                self.inventory.add_host(hostname)
                for var_name, var_val in hvars.items():
                    self.inventory.set_variable(hostname, var_name, var_val)
                # Add host to its groups
                for group_name in ["ipaserver", "ipaclient", "arbiter_hub", "arbiter_agent"]:
                    if hostname in inv.get(group_name, {}).get("hosts", []):
                        self.inventory.add_host(hostname, group=group_name)


# Standalone mode: python idmci_inventory.py --list
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IdM-CI dynamic inventory")
    parser.add_argument("--list", action="store_true", help="Output full inventory")
    parser.add_argument("--host", help="Output host vars for a single host")
    parser.add_argument("--metadata", default="idm-ci/metadata-arbiter-demo-3node.yaml",
                        help="Path to IdM-CI metadata YAML")
    parser.add_argument("--beaker-job", default=None,
                        help="Beaker job ID (J:NNNN) for live IP lookup")
    parser.add_argument("--ssh-key", default="~/.ssh/idm_ci_key",
                        help="SSH private key path")
    parser.add_argument("--domain", default=None,
                        help="Override domain from metadata")
    args = parser.parse_args()

    inv = build_inventory(
        metadata_path=args.metadata,
        beaker_job_id=args.beaker_job,
        ssh_key_file=args.ssh_key,
        domain_override=args.domain,
    )

    if args.host:
        hostvars = inv.get("_meta", {}).get("hostvars", {}).get(args.host, {})
        print(json.dumps(hostvars, indent=2))
    else:
        print(json.dumps(inv, indent=2))
