#!/usr/bin/env python3
"""
ServiceNow webhook receiver for Arbiter Hub EDA events.

Receives OCSF v1.3 security events from Hub EDA controller and creates
ServiceNow incidents for state transitions indicating trust violations.

Usage:
    export SNOW_INSTANCE=dev12345.service-now.com
    export SNOW_USER=api_user
    export SNOW_PASSWORD=api_password
    export SNOW_ASSIGNMENT_GROUP="Security Operations"
    python3 servicenow-webhook.py [--port 8080]

Hub EDA configuration:
    Point EDA webhook to http://<this-host>:8080/webhook
"""

import json
import os
import sys
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from base64 import b64encode
from datetime import datetime

SNOW_INSTANCE = os.environ.get("SNOW_INSTANCE", "")
SNOW_USER = os.environ.get("SNOW_USER", "")
SNOW_PASSWORD = os.environ.get("SNOW_PASSWORD", "")
SNOW_ASSIGNMENT_GROUP = os.environ.get("SNOW_ASSIGNMENT_GROUP", "Security Operations")

ALERT_STATES = {"SUSPECT", "QUARANTINED", "REVOKED"}

SEVERITY_MAP = {
    "SUSPECT": "3",
    "QUARANTINED": "2",
    "REVOKED": "1",
}

# Example OCSF v1.3 event payloads for testing:
EXAMPLE_SUSPECT = {
    "class_uid": 2001,
    "class_name": "Security Finding",
    "category_uid": 2,
    "category_name": "Findings",
    "severity_id": 3,
    "activity_id": 1,
    "activity_name": "Create",
    "time": "2026-11-09T15:30:00Z",
    "message": "Workload state transition: ATTESTED → SUSPECT",
    "finding": {
        "title": "Attestation Failure",
        "desc": "TPM quote verification failed for workload web-frontend",
        "uid": "arbiter-hub-001",
    },
    "resources": [
        {
            "type": "workload",
            "name": "web-frontend",
            "uid": "wl-12345",
        }
    ],
    "metadata": {
        "product": {"name": "Arbiter Hub", "vendor_name": "Red Hat"},
        "version": "1.3.0",
    },
}

EXAMPLE_QUARANTINED = {
    **EXAMPLE_SUSPECT,
    "severity_id": 4,
    "message": "Workload state transition: SUSPECT → QUARANTINED",
    "finding": {
        "title": "Workload Quarantined",
        "desc": "IMA measurement mismatch detected on workload db-server",
        "uid": "arbiter-hub-002",
    },
    "resources": [
        {"type": "workload", "name": "db-server", "uid": "wl-67890"}
    ],
}


def create_snow_incident(event):
    """Map OCSF event to ServiceNow Incident API call."""
    if not all([SNOW_INSTANCE, SNOW_USER, SNOW_PASSWORD]):
        print(f"SNOW not configured — would create incident for: "
              f"{event.get('message', 'unknown')}")
        return None

    resources = event.get("resources", [{}])
    workload_name = resources[0].get("name", "unknown") if resources else "unknown"
    finding = event.get("finding", {})
    new_state = event.get("message", "").split("→")[-1].strip() if "→" in event.get("message", "") else "UNKNOWN"

    incident = {
        "short_description": f"Arbiter Hub: {workload_name} — {finding.get('title', 'Attestation Event')}",
        "description": (
            f"Workload: {workload_name}\n"
            f"State: {new_state}\n"
            f"Detail: {finding.get('desc', 'No details')}\n"
            f"Time: {event.get('time', 'unknown')}\n"
            f"Finding ID: {finding.get('uid', 'none')}\n"
        ),
        "category": "Security",
        "subcategory": "Attestation Failure",
        "impact": SEVERITY_MAP.get(new_state, "3"),
        "urgency": SEVERITY_MAP.get(new_state, "3"),
        "assignment_group": SNOW_ASSIGNMENT_GROUP,
        "caller_id": SNOW_USER,
    }

    url = f"https://{SNOW_INSTANCE}/api/now/table/incident"
    creds = b64encode(f"{SNOW_USER}:{SNOW_PASSWORD}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {creds}",
    }

    data = json.dumps(incident).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            inc_number = result.get("result", {}).get("number", "unknown")
            print(f"Incident created: {inc_number} for {workload_name} ({new_state})")
            return inc_number
    except urllib.error.URLError as e:
        print(f"Failed to create incident: {e}", file=sys.stderr)
        return None


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "invalid JSON"}')
            return

        message = event.get("message", "")
        new_state = message.split("→")[-1].strip() if "→" in message else ""

        print(f"[{datetime.now().isoformat()}] Received: {message}")

        if new_state in ALERT_STATES:
            inc = create_snow_incident(event)
            resp = {"status": "incident_created", "incident": inc}
        else:
            resp = {"status": "acknowledged", "action": "none"}
            print(f"  State '{new_state}' not alertable — acknowledged")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    port = 8080
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])

    if "--test" in sys.argv:
        print("=== Testing with example SUSPECT event ===")
        create_snow_incident(EXAMPLE_SUSPECT)
        print("\n=== Testing with example QUARANTINED event ===")
        create_snow_incident(EXAMPLE_QUARANTINED)
        return

    print(f"ServiceNow webhook receiver starting on port {port}")
    print(f"SNOW instance: {SNOW_INSTANCE or '(not configured — dry mode)'}")
    print(f"Listening for POST /webhook from Hub EDA")

    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()


if __name__ == "__main__":
    main()
