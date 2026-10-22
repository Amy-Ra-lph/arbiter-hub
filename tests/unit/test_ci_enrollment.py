import pytest

from server.auth.models import CallerIdentity
from server.auth.rbac import check_permission


def test_ci_enroll_permission_in_pipeline_role():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "ci_enroll" in ROLE_PERMISSIONS["attestation-pipeline"]


def test_ci_enroll_permission_in_admin_role():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "ci_enroll" in ROLE_PERMISSIONS["attestation-admin"]


def test_ci_enroll_permission_not_in_viewer():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "ci_enroll" not in ROLE_PERMISSIONS["attestation-viewer"]


def test_ci_enroll_permission_not_in_agent():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "ci_enroll" not in ROLE_PERMISSIONS["attestation-agent"]


def test_ci_enroll_permission_not_in_operator():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "ci_enroll" not in ROLE_PERMISSIONS["attestation-operator"]


def test_pipeline_can_ci_enroll():
    identity = CallerIdentity(
        principal="carol@ARBITER.DEMO",
        actor_type="pipeline",
        roles=["attestation-pipeline"],
        scopes=["*"],
    )
    assert check_permission(identity, "ci_enroll") is True


def test_admin_can_ci_enroll():
    identity = CallerIdentity(
        principal="alice@ARBITER.DEMO",
        actor_type="admin",
        roles=["attestation-admin"],
        scopes=["*"],
    )
    assert check_permission(identity, "ci_enroll") is True


def test_viewer_cannot_ci_enroll():
    identity = CallerIdentity(
        principal="dave@ARBITER.DEMO",
        actor_type="user",
        roles=["attestation-viewer"],
        scopes=["*"],
    )
    assert check_permission(identity, "ci_enroll") is False


def test_agent_cannot_ci_enroll():
    identity = CallerIdentity(
        principal="eve@ARBITER.DEMO",
        actor_type="agent",
        roles=["attestation-agent"],
        scopes=["*"],
    )
    assert check_permission(identity, "ci_enroll") is False


def test_ci_enroll_request_schema_valid():
    from server.api.ci_enrollment import CIEnrollRequest

    req = CIEnrollRequest(
        ipa_principal="ci/test-app@ARBITER.DEMO",
        display_name="Test CI App",
        workload_type="bootc",
        backend_types=["cosign"],
        artifact_ref="quay.io/test/app:latest",
        image_digest="sha256:abc123",
        auto_attest=True,
    )
    assert req.ipa_principal == "ci/test-app@ARBITER.DEMO"
    assert req.workload_type.value == "bootc"
    assert req.backend_types == ["cosign"]


def test_ci_enroll_request_schema_invalid_principal():
    from pydantic import ValidationError

    from server.api.ci_enrollment import CIEnrollRequest

    with pytest.raises(ValidationError):
        CIEnrollRequest(
            ipa_principal="invalid principal with spaces!",
            display_name="Test",
            workload_type="service",
            backend_types=["keylime"],
        )


def test_ci_enroll_request_schema_empty_backends():
    from pydantic import ValidationError

    from server.api.ci_enrollment import CIEnrollRequest

    with pytest.raises(ValidationError):
        CIEnrollRequest(
            ipa_principal="ci/test@ARBITER.DEMO",
            display_name="Test",
            workload_type="service",
            backend_types=[],
        )


def test_ci_enroll_request_schema_missing_principal():
    from pydantic import ValidationError

    from server.api.ci_enrollment import CIEnrollRequest

    with pytest.raises(ValidationError):
        CIEnrollRequest(
            display_name="Missing Principal",
            workload_type="service",
            backend_types=["keylime"],
        )


def test_ci_enroll_response_schema():
    import uuid

    from server.api.ci_enrollment import CIEnrollResponse

    resp = CIEnrollResponse(
        workload_id=uuid.uuid4(),
        state="registered",
        attestation_triggered=False,
        backends_registered=["cosign", "falco"],
        detail={"action": "created"},
    )
    assert resp.state.value == "registered"
    assert len(resp.backends_registered) == 2


def test_ci_enroll_request_defaults():
    from server.api.ci_enrollment import CIEnrollRequest

    req = CIEnrollRequest(
        ipa_principal="ci/minimal@ARBITER.DEMO",
        display_name="Minimal",
        workload_type="service",
        backend_types=["keylime"],
    )
    assert req.artifact_ref == ""
    assert req.image_digest == ""
    assert req.metadata == {}
    assert req.auto_attest is True


@pytest.mark.asyncio
async def test_ci_enroll_endpoint_registered():
    from httpx import ASGITransport, AsyncClient

    from server.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        assert "/ci/enroll" in paths
        assert "post" in paths["/ci/enroll"]
