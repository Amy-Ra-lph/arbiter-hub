from server.models.db import (
    AttestationVerdict,
    BackendType,
    WorkloadState,
    WorkloadType,
)
from server.models.schemas import PaginatedResponse, WorkloadCreate, WorkloadRead


def test_workload_state_enum_has_seven_states():
    assert len(WorkloadState) == 7
    assert WorkloadState.REGISTERED.value == "registered"
    assert WorkloadState.ATTESTING.value == "attesting"
    assert WorkloadState.HEALTHY.value == "healthy"
    assert WorkloadState.STALE.value == "stale"
    assert WorkloadState.FAILED.value == "failed"
    assert WorkloadState.UNDER_REMEDIATION.value == "under_remediation"
    assert WorkloadState.REVOKED.value == "revoked"


def test_workload_type_enum():
    assert set(w.value for w in WorkloadType) == {"agentic", "cvm", "service"}


def test_attestation_verdict_enum():
    assert set(v.value for v in AttestationVerdict) == {"pass", "fail", "error", "unavailable"}


def test_backend_type_enum():
    assert set(b.value for b in BackendType) == {"keylime", "trustee", "cosign", "rekor", "falco"}


def test_workload_create_schema():
    wc = WorkloadCreate(
        ipa_principal="agent-foo@EXAMPLE.COM",
        display_name="Agent Foo",
        workload_type=WorkloadType.AGENTIC,
        backend_type="keylime",
    )
    assert wc.ipa_principal == "agent-foo@EXAMPLE.COM"
    assert wc.backend_types == [BackendType.KEYLIME]


def test_paginated_response():
    pr = PaginatedResponse[WorkloadRead](items=[], total=0, start_index=1, count=25)
    assert pr.total == 0
