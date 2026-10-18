import asyncio
import hashlib
import logging

from datetime import datetime, timezone
from server.backends.base import (
    AttestationResult,
    EnrollResult,
    RevokeResult,
    BackendHealth,
)
from server.models.db import AttestationVerdict, Workload

log = logging.getLogger(__name__)


class CosignBackend:
    def __init__(
        self,
        cosign_binary: str = "cosign",
        rekor_url: str = "",
        fulcio_url: str = "",
        tuf_root: str = "",
    ):
        self._binary = cosign_binary
        self._rekor_url = rekor_url
        self._fulcio_url = fulcio_url
        self._tuf_root = tuf_root

    async def verify(self, workload: Workload) -> AttestationResult:
        artifact_ref = workload.metadata_.get("artifact_ref", "")
        if not artifact_ref:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="cosign",
                evidence_hash="",
                detail={"error": "no artifact_ref in workload metadata"},
            )
        try:
            cmd = [self._binary, "verify", "--yes", artifact_ref]
            if self._rekor_url:
                cmd.extend(["--rekor-url", self._rekor_url])
            if self._fulcio_url:
                cmd.extend(["--fulcio-url", self._fulcio_url])
            if self._tuf_root:
                cmd.extend(["--tuf-root", self._tuf_root])
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            evidence_hash = hashlib.sha256(stdout).hexdigest()
            if proc.returncode == 0:
                return AttestationResult(
                    verdict=AttestationVerdict.PASS,
                    backend="cosign",
                    evidence_hash=evidence_hash,
                    detail={"output": stdout.decode()[:500]},
                )
            else:
                return AttestationResult(
                    verdict=AttestationVerdict.FAIL,
                    backend="cosign",
                    evidence_hash=evidence_hash,
                    detail={"error": stderr.decode()[:500]},
                )
        except asyncio.TimeoutError:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="cosign",
                evidence_hash="",
                detail={"error": "cosign verify timed out"},
            )
        except FileNotFoundError:
            return AttestationResult(
                verdict=AttestationVerdict.UNAVAILABLE,
                backend="cosign",
                evidence_hash="",
                detail={"error": f"cosign binary not found: {self._binary}"},
            )

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        return EnrollResult(
            success=True,
            backend="cosign",
            detail={"note": "cosign has no enrollment — verify on demand"},
        )

    async def revoke(self, workload: Workload) -> RevokeResult:
        return RevokeResult(
            success=True,
            backend="cosign",
            detail={"note": "cosign has no revocation — signatures are permanent"},
        )

    async def health(self) -> BackendHealth:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return BackendHealth(
                healthy=proc.returncode == 0,
                backend="cosign",
                last_check=datetime.now(timezone.utc),
                detail=stdout.decode().strip().split("\n")[0]
                if proc.returncode == 0
                else "cosign unhealthy",
            )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                backend="cosign",
                last_check=datetime.now(timezone.utc),
                detail=str(e),
            )
