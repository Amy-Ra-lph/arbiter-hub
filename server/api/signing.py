import asyncio
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_OCI_REF_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9._/-]*[a-zA-Z0-9])?(@sha256:[a-f0-9]{64})?(:[a-zA-Z0-9._-]+)?$"
)
_KEY_PATH_RE = re.compile(r"^[a-zA-Z0-9._/:-]+$")


def _validate_ref(v: str) -> str:
    if v.startswith("-"):
        raise ValueError("artifact_ref must not start with '-'")
    if not _OCI_REF_RE.match(v):
        raise ValueError("artifact_ref must be a valid OCI reference")
    return v


class SignRequest(BaseModel):
    artifact_ref: str
    key_ref: str | None = None

    @field_validator("artifact_ref")
    @classmethod
    def check_artifact_ref(cls, v: str) -> str:
        return _validate_ref(v)

    @field_validator("key_ref")
    @classmethod
    def check_key_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v.startswith("-"):
            raise ValueError("key_ref must not start with '-'")
        if not _KEY_PATH_RE.match(v):
            raise ValueError("key_ref contains invalid characters")
        if ".." in v:
            raise ValueError("key_ref must not contain path traversal")
        return v


class VerifyRequest(BaseModel):
    artifact_ref: str

    @field_validator("artifact_ref")
    @classmethod
    def check_artifact_ref(cls, v: str) -> str:
        return _validate_ref(v)


@router.post("/sign")
@limiter.limit("5/minute")
async def sign_artifact(
    request: Request,
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
@limiter.limit("20/minute")
async def verify_artifact(
    request: Request,
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
