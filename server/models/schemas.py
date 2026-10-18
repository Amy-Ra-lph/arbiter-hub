import uuid
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, Field

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
    ipa_principal: str
    display_name: str
    workload_type: WorkloadType
    backend_type: BackendType
    stale_ttl_seconds: int = 3600
    metadata: dict = Field(default_factory=dict)


class WorkloadRead(BaseModel):
    id: uuid.UUID
    ipa_principal: str
    display_name: str
    workload_type: WorkloadType
    current_state: WorkloadState
    backend_type: BackendType
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
    name: str
    policy_type: str = "simple"
    policy_content: dict
    scope: str | None = None


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
    repo: str
    secret_type: str
    tag: str
    value: str  # plaintext — server encrypts before storage
    required_state: WorkloadState = WorkloadState.HEALTHY
    workload_scope: str | None = None


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
