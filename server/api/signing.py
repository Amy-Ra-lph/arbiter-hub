import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity

router = APIRouter()


class SignRequest(BaseModel):
    artifact_ref: str
    key_ref: str | None = None


class VerifyRequest(BaseModel):
    artifact_ref: str


@router.post("/sign")
async def sign_artifact(
    body: SignRequest,
    caller: CallerIdentity = require_permission("sign_artifact"),
):
    """Sign a container artifact using cosign."""
    cmd = ["cosign", "sign", "--yes", body.artifact_ref]
    if body.key_ref:
        cmd.extend(["--key", body.key_ref])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="cosign sign operation timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="cosign binary not found")

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"cosign sign failed: {stderr.decode()[:500]}")

    return {
        "status": "signed",
        "artifact_ref": body.artifact_ref,
        "output": stdout.decode()[:500],
    }


@router.post("/verify")
async def verify_artifact(
    body: VerifyRequest,
    caller: CallerIdentity = require_permission("verify_artifact"),
):
    """Verify a container artifact signature using cosign."""
    cmd = ["cosign", "verify", body.artifact_ref]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="cosign verify operation timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="cosign binary not found")

    if proc.returncode == 0:
        return {
            "verified": True,
            "artifact_ref": body.artifact_ref,
            "output": stdout.decode()[:500],
        }
    else:
        return {
            "verified": False,
            "artifact_ref": body.artifact_ref,
            "error": stderr.decode()[:500],
        }
