import pytest
from pydantic import ValidationError

from server.models.db import BackendType
from server.models.schemas import WorkloadCreate


def test_falco_backend_type_exists():
    assert BackendType.FALCO == "falco"


def test_workload_create_accepts_backend_types_list():
    wc = WorkloadCreate(
        ipa_principal="svc/host@REALM",
        display_name="test",
        workload_type="service",
        backend_types=["keylime", "cosign"],
    )
    assert wc.backend_types == [BackendType.KEYLIME, BackendType.COSIGN]


def test_create_workload_singular_backend_type_compat():
    wc = WorkloadCreate(
        ipa_principal="svc/host@REALM",
        display_name="test",
        workload_type="service",
        backend_type="keylime",
    )
    assert wc.backend_types == [BackendType.KEYLIME]


def test_create_workload_empty_backend_types_rejected():
    with pytest.raises(ValidationError):
        WorkloadCreate(
            ipa_principal="svc/host@REALM",
            display_name="test",
            workload_type="service",
            backend_types=[],
        )
