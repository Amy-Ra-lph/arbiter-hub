# arbiter_mcp/client.py
import httpx
from typing import Any


class ArbiterClient:
    def __init__(self, base_url: str, headers: dict | None = None):
        self._base_url = base_url.rstrip("/")
        self._headers = headers or {}

    async def get_workload(self, workload_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/workloads/{workload_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_workloads(self, state: str | None = None) -> dict:
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/workloads",
                params=params,
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def check_compliance(self, workload_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/workloads/{workload_id}/compliance",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def verify_artifact(self, artifact_ref: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/verify",
                json={"artifact_ref": artifact_ref},
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def query_audit(self, actor: str | None = None, action: str | None = None) -> dict:
        params: dict[str, Any] = {}
        if actor:
            params["actor"] = actor
        if action:
            params["action"] = action
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/audit",
                params=params,
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def backend_health(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/backends",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
