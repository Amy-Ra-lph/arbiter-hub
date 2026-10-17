from dataclasses import dataclass
from server.models.db import WorkloadState
from server.policy.engine import PolicyEngine, PolicyDecision


@dataclass
class GateResult:
    allowed: bool
    reason: str


async def check_kbs_gate(
    workload_state: WorkloadState,
    attestation_age_seconds: float,
    policy_engine: PolicyEngine | None,
    subject: str,
    resource: str,
    max_attestation_age: int = 3600,
) -> GateResult:
    if workload_state != WorkloadState.HEALTHY:
        return GateResult(allowed=False, reason=f"workload state is {workload_state.value}, must be healthy")

    if attestation_age_seconds > max_attestation_age:
        return GateResult(allowed=False, reason=f"attestation age {attestation_age_seconds}s exceeds max {max_attestation_age}s")

    if policy_engine:
        decision = await policy_engine.evaluate(
            subject=subject,
            action="kbs_release",
            resource=resource,
            context={
                "workload_state": workload_state.value,
                "attestation_age": attestation_age_seconds,
            },
        )
        if not decision.allowed:
            return GateResult(allowed=False, reason=decision.reason)

    return GateResult(allowed=True, reason="all checks passed")
