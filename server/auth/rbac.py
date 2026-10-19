from server.auth.models import CallerIdentity, Role

ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "read_workload",
        "register_workload",
        "trigger_attestation",
        "revoke_workload",
        "remediate_workload",
        "sign_artifact",
        "verify_artifact",
        "create_policy",
        "update_policy",
        "read_audit",
        "read_backends",
        "read_compliance",
        "request_reattest",
        "manage_kbs",
        "register_webhook",
    },
    Role.OPERATOR.value: {
        "read_workload",
        "register_workload",
        "trigger_attestation",
        "remediate_workload",
        "verify_artifact",
        "read_audit",
        "read_backends",
        "read_compliance",
        "request_reattest",
    },
    Role.PIPELINE.value: {
        "read_workload",
        "trigger_attestation",
        "sign_artifact",
        "verify_artifact",
        "read_compliance",
        "read_backends",
    },
    Role.VIEWER.value: {
        "read_workload",
        "read_audit",
        "read_backends",
        "read_compliance",
        "verify_artifact",
    },
    Role.AGENT.value: {
        "read_workload",
        "read_compliance",
        "read_backends",
        "verify_artifact",
        "read_audit",
        "request_reattest",
    },
}


def check_permission(identity: CallerIdentity, action: str) -> bool:
    for role in identity.roles:
        permissions = ROLE_PERMISSIONS.get(role, set())
        if action in permissions:
            return True
    return False


def check_scope(identity: CallerIdentity, workload_scope: str) -> bool:
    if Role.ADMIN.value in identity.roles:
        return True
    if "*" in identity.scopes:
        return True
    return workload_scope in identity.scopes
