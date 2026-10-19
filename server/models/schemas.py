import uuid
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, Field, StringConstraints, model_validator
from typing_extensions import Annotated

ConstrainedName = Annotated[str, StringConstraints(min_length=1, max_length=255)]
ConstrainedPrincipal = Annotated[str, StringConstraints(min_length=1, max_length=512)]
ConstrainedText = Annotated[str, StringConstraints(max_length=4096)]

from server.models.db import AttestationVerdict, BackendType, WorkloadState, WorkloadType

T = TypeVar("T")


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    start_index: int = 1
    count: int = 25


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None


class WorkloadCreate(BaseModel):
    ipa_principal: ConstrainedPrincipal
    display_name: ConstrainedName
    workload_type: WorkloadType
    backend_types: list[BackendType] = Field(min_length=1, max_length=10)
    stale_ttl_seconds: int = Field(default=3600, ge=60, le=604800)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _compat_singular(cls, data):
        if isinstance(data, dict) and "backend_type" in data and "backend_types" not in data:
            data["backend_types"] = [data.pop("backend_type")]
        return data


class WorkloadRead(BaseModel):
    id: uuid.UUID
    ipa_principal: str
    display_name: str
    workload_type: WorkloadType
    current_state: WorkloadState
    backend_types: list[str]
    stale_ttl_seconds: int
    registered_at: datetime
    last_attested_at: datetime | None
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_")

    model_config = {"from_attributes": True}


class WorkloadList(PaginatedResponse[WorkloadRead]):
    pass


class AttestationRecordRead(BaseModel):
    id: uuid.UUID
    workload_id: uuid.UUID
    backend: BackendType
    verdict: AttestationVerdict
    evidence_hash: str | None
    policy_hash: str | None
    detail: dict
    rekor_entry_uuid: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StateTransitionRead(BaseModel):
    id: uuid.UUID
    workload_id: uuid.UUID
    from_state: WorkloadState
    to_state: WorkloadState
    triggered_by: str
    justification: str | None
    rekor_entry_uuid: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    name: ConstrainedName
    policy_type: ConstrainedName = "simple"
    policy_content: dict
    scope: ConstrainedName | None = None
    active: bool = True


class PolicyRead(BaseModel):
    id: uuid.UUID
    name: str
    policy_type: str
    policy_content: dict
    scope: str | None
    active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuditLogRead(BaseModel):
    id: uuid.UUID
    actor: str
    actor_type: str
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class KBSSecretCreate(BaseModel):
    repo: ConstrainedName
    secret_type: ConstrainedName
    tag: ConstrainedName
    value: Annotated[str, StringConstraints(min_length=1, max_length=65536)]
    required_state: WorkloadState = WorkloadState.HEALTHY
    workload_scope: ConstrainedName | None = None


class KBSSecretRead(BaseModel):
    id: uuid.UUID
    repo: str
    secret_type: str
    tag: str
    required_state: WorkloadState
    workload_scope: str | None
    created_by: str
    created_at: datetime
    rotated_at: datetime | None

    model_config = {"from_attributes": True}


class ComplianceResult(BaseModel):
    workload_id: uuid.UUID
    compliant: bool
    checks: list[dict]
    evaluated_at: datetime


class GateCheckResult(BaseModel):
    workload_id: uuid.UUID
    gate_passed: bool
    state: WorkloadState
    compliance: ComplianceResult
    attestation_current: bool
    detail: dict
