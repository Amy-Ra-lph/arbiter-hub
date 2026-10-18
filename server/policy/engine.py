from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class PolicyDecision:
    allowed: bool
    obligations: list[str] = field(default_factory=list)
    reason: str = ""


@runtime_checkable
class PolicyEngine(Protocol):
    async def evaluate(
        self, subject: str, action: str, resource: str, context: dict
    ) -> PolicyDecision: ...


class SimpleRulesEngine:
    def __init__(self, policies: list[dict]):
        self._policies = policies

    async def evaluate(
        self, subject: str, action: str, resource: str, context: dict
    ) -> PolicyDecision:
        for policy in self._policies:
            for rule in policy.get("rules", []):
                if rule.get("action") != action:
                    continue
                requirements = rule.get("require", {})
                if self._check_requirements(requirements, context):
                    return PolicyDecision(
                        allowed=True,
                        obligations=policy.get("obligations", []),
                        reason=f"matched policy '{policy['name']}'",
                    )
                else:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"policy '{policy['name']}' requirements not met",
                    )
        return PolicyDecision(allowed=False, reason="no matching policy for action")

    def _check_requirements(self, requirements: dict, context: dict) -> bool:
        for key, expected in requirements.items():
            actual = context.get(key)
            if key == "attestation_age_max":
                age = context.get("attestation_age", float("inf"))
                if age > expected:
                    return False
            elif isinstance(expected, list):
                if actual not in expected:
                    return False
            elif isinstance(expected, bool):
                if actual != expected:
                    return False
            else:
                if actual != expected:
                    return False
        return True
