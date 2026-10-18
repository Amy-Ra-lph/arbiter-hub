from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "attestation-admin"
    OPERATOR = "attestation-operator"
    PIPELINE = "attestation-pipeline"
    VIEWER = "attestation-viewer"
    AGENT = "attestation-agent"


@dataclass
class CallerIdentity:
    principal: str
    actor_type: str  # "admin", "pipeline", "agent"
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
