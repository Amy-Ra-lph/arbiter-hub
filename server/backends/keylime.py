import hashlib
import logging
from datetime import datetime, timezone
import httpx
from server.backends.base import (
    AttestationBackend, AttestationResult, EnrollResult, RevokeResult, BackendHealth,
)
from server.models.db import AttestationVerdict, Workload

log = logging.getLogger(__name__)


class KeylimeBackend:
    def __init__(
        self,
        verifier_url: str,
        ca_cert: str,
        client_cert: str,
        client_key: str,
        timeout: float = 10.0,
    ):
        self._verifier_url = verifier_url.rstrip("/")
        self._ca_cert = ca_cert
        self._client_cert = client_cert
        self._client_key = client_key
        self._timeout = timeout

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": self._timeout, "verify": False}
        if self._ca_cert and self._client_cert and self._client_key:
            kwargs["verify"] = self._ca_cert
            kwargs["cert"] = (self._client_cert, self._client_key)
        return httpx.AsyncClient(**kwargs)

    async def verify(self, workload: Workload) -> AttestationResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        if not agent_id:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="keylime",
                evidence_hash="",
                detail={"error": "no keylime_agent_uuid in workload metadata"},
            )
        try:
            async with self._build_client() as client:
                resp = await client.get(f"{self._verifier_url}/v2.1/agents/{agent_id}")
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", {})
                op_state = results.get("operational_state", -1)
                # Keylime op_state: 7 = GET_QUOTE (attesting), others vary
                # A healthy agent has op_state that indicates verified
                ima_hash = hashlib.sha256(str(results).encode()).hexdigest()
                if op_state in (7, 8, 9):  # verified states
                    verdict = AttestationVerdict.PASS
                else:
                    verdict = AttestationVerdict.FAIL
                return AttestationResult(
                    verdict=verdict,
                    backend="keylime",
                    evidence_hash=ima_hash,
                    detail={"operational_state": op_state, "agent_id": agent_id},
                )
        except httpx.HTTPError as e:
            log.warning("Keylime verify failed for %s: %s", agent_id, e)
            return AttestationResult(
                verdict=AttestationVerdict.UNAVAILABLE,
                backend="keylime",
                evidence_hash="",
                detail={"error": str(e)},
            )

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        agent_ip = workload.metadata_.get("keylime_agent_ip", "")
        if not agent_id or not agent_ip:
            return EnrollResult(
                success=False,
                backend="keylime",
                detail={"error": "keylime_agent_uuid and keylime_agent_ip required in metadata"},
            )
        try:
            async with self._build_client() as client:
                payload = {
                    "v": "2.1",
                    "agent_id": agent_id,
                    "ip": agent_ip,
                    "tpm_policy": policy.get("tpm_policy", "{}"),
                    "runtime_policy": policy.get("runtime_policy", ""),
                }
                resp = await client.post(f"{self._verifier_url}/v2.1/agents/{agent_id}", json=payload)
                resp.raise_for_status()
                return EnrollResult(success=True, backend="keylime", detail=resp.json())
        except httpx.HTTPError as e:
            return EnrollResult(success=False, backend="keylime", detail={"error": str(e)})

    async def revoke(self, workload: Workload) -> RevokeResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        if not agent_id:
            return RevokeResult(success=False, backend="keylime", detail={"error": "no agent_id"})
        try:
            async with self._build_client() as client:
                resp = await client.delete(f"{self._verifier_url}/v2.1/agents/{agent_id}")
                resp.raise_for_status()
                return RevokeResult(success=True, backend="keylime", detail=resp.json())
        except httpx.HTTPError as e:
            return RevokeResult(success=False, backend="keylime", detail={"error": str(e)})

    async def health(self) -> BackendHealth:
        try:
            async with self._build_client() as client:
                resp = await client.get(f"{self._verifier_url}/v2.1/agents/")
                resp.raise_for_status()
                return BackendHealth(
                    healthy=True,
                    backend="keylime",
                    last_check=datetime.now(timezone.utc),
                    detail=f"verifier reachable, {len(resp.json().get('results', {}).get('uuids', []))} agents",
                )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                backend="keylime",
                last_check=datetime.now(timezone.utc),
                detail=str(e),
            )
