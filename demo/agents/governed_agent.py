#!/usr/bin/env python3
"""Well-behaved agentic workload: authenticates, attests, uses MCP tools within sandbox boundaries."""

import argparse
import asyncio
import json
import sys
import time
from uuid import uuid4

import httpx


def log_event(action: str, **kwargs):
    print(json.dumps({"ts": time.time(), "agent": "governed", "action": action, **kwargs}), flush=True)


class GovernedAgent:
    def __init__(self, hub_url: str, idp_url: str, client_id: str, client_secret: str, target_host: str):
        self.hub_url = hub_url.rstrip("/")
        self.idp_url = idp_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.target_host = target_host
        self.token = ""
        self.workload_id = ""
        self.principal = f"agent/governed-{uuid4().hex[:8]}@ARBITER.DEMO"

    async def authenticate(self, client: httpx.AsyncClient) -> str:
        log_event("authenticate", idp=self.idp_url)
        discovery = await client.get(f"{self.idp_url}/.well-known/openid-configuration")
        discovery.raise_for_status()
        token_endpoint = discovery.json()["token_endpoint"]

        resp = await client.post(token_endpoint, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "openid profile attestation-agent",
        })
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        log_event("authenticated", token_len=len(self.token))
        return self.token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def register_workload(self, client: httpx.AsyncClient) -> str:
        log_event("register_workload", principal=self.principal)
        resp = await client.post(f"{self.hub_url}/workloads", headers=self._auth_headers(), json={
            "ipa_principal": self.principal,
            "display_name": f"Governed Agent ({self.principal.split('/')[1].split('@')[0]})",
            "workload_type": "agentic",
            "backend_types": ["falco"],
            "metadata": {
                "agent_type": "governed",
                "sandbox": "wid-sovereign",
                "managed_by": "governed_agent.py",
            },
        })
        if resp.status_code == 409:
            log_event("workload_exists", principal=self.principal)
            search = await client.get(f"{self.hub_url}/workloads", headers=self._auth_headers())
            search.raise_for_status()
            for w in search.json().get("items", []):
                if w["ipa_principal"] == self.principal:
                    self.workload_id = w["id"]
                    return self.workload_id
        resp.raise_for_status()
        self.workload_id = resp.json()["id"]
        log_event("registered", workload_id=self.workload_id)
        return self.workload_id

    async def request_attestation(self, client: httpx.AsyncClient) -> dict:
        log_event("request_attestation", workload_id=self.workload_id)
        resp = await client.post(
            f"{self.hub_url}/workloads/{self.workload_id}/attest",
            headers=self._auth_headers(),
        )
        if resp.status_code == 409:
            log_event("attestation_state_conflict", detail=resp.text)
            return {"verdict": "skipped", "reason": resp.text}
        resp.raise_for_status()
        result = resp.json()
        log_event("attested", verdict=result.get("verdict"), state=result.get("state"))
        return result

    async def check_kbs_secret(self, client: httpx.AsyncClient, resource: str) -> dict | None:
        log_event("kbs_request", resource=resource, workload_id=self.workload_id)
        resp = await client.get(
            f"{self.hub_url}/kbs/v0/resources/{resource}",
            headers=self._auth_headers(),
            params={"workload_id": self.workload_id},
        )
        if resp.status_code == 403:
            log_event("kbs_denied", resource=resource, reason=resp.text)
            return None
        if resp.status_code == 404:
            log_event("kbs_not_found", resource=resource)
            return None
        resp.raise_for_status()
        log_event("kbs_released", resource=resource)
        return resp.json()

    async def call_mcp_tool(self, client: httpx.AsyncClient, mcp_url: str, tool: str, args: dict) -> dict:
        log_event("mcp_call", tool=tool, args=args)
        resp = await client.post(f"{mcp_url}/tools/call", json={"name": tool, "arguments": args})
        if resp.status_code != 200:
            log_event("mcp_error", tool=tool, status=resp.status_code, body=resp.text[:200])
            return {"error": resp.text[:200]}
        result = resp.json()
        log_event("mcp_result", tool=tool, content_len=len(str(result)))
        return result

    async def run_diagnostic_cycle(self):
        log_event("cycle_start", target=self.target_host)
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            await self.authenticate(client)
            await self.register_workload(client)
            attestation = await self.request_attestation(client)

            secret = await self.check_kbs_secret(client, "diagnostic-api-key")
            if secret:
                log_event("secret_available", resource="diagnostic-api-key")
            else:
                log_event("proceeding_without_secret")

            mcp_url = f"http://{self.target_host}:8402"
            await self.call_mcp_tool(client, mcp_url, "systemctl_status", {"unit": "sshd"})
            await self.call_mcp_tool(client, mcp_url, "ps_aux", {})
            await self.call_mcp_tool(client, mcp_url, "df_usage", {})
            await self.call_mcp_tool(client, mcp_url, "selinux_status", {})

            log_event("cycle_complete", attestation_verdict=attestation.get("verdict", "unknown"))


def main():
    parser = argparse.ArgumentParser(description="Governed agentic workload for Arbiter Hub demo")
    parser.add_argument("--hub-url", default="http://hub.arbiter.demo:8400", help="Arbiter Hub API URL")
    parser.add_argument("--idp-url", default="https://idm.arbiter.demo/idp", help="ahdapa OIDC issuer URL")
    parser.add_argument("--client-id", default="arbiter-hub", help="OAuth2 client ID")
    parser.add_argument("--client-secret", required=True, help="OAuth2 client secret")
    parser.add_argument("--target-host", default="agent.arbiter.demo", help="Target host for MCP diagnostics")
    parser.add_argument("--loop", type=int, default=0, help="Loop interval in seconds (0=single run)")
    args = parser.parse_args()

    agent = GovernedAgent(
        hub_url=args.hub_url,
        idp_url=args.idp_url,
        client_id=args.client_id,
        client_secret=args.client_secret,
        target_host=args.target_host,
    )

    if args.loop > 0:
        async def loop():
            while True:
                try:
                    await agent.run_diagnostic_cycle()
                except Exception as e:
                    log_event("cycle_error", error=str(e))
                await asyncio.sleep(args.loop)
        asyncio.run(loop())
    else:
        asyncio.run(agent.run_diagnostic_cycle())


if __name__ == "__main__":
    main()
