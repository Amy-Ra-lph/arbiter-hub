import enum
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from server.config import settings


class WorkloadType(enum.StrEnum):
    AGENTIC = "agentic"
    CVM = "cvm"
    SERVICE = "service"


class WorkloadState(enum.StrEnum):
    REGISTERED = "registered"
    ATTESTING = "attesting"
    HEALTHY = "healthy"
    STALE = "stale"
    FAILED = "failed"
    UNDER_REMEDIATION = "under_remediation"
    REVOKED = "revoked"


class AttestationVerdict(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class BackendType(enum.StrEnum):
    KEYLIME = "keylime"
    TRUSTEE = "trustee"
    COSIGN = "cosign"
    REKOR = "rekor"
    FALCO = "falco"


class Base(DeclarativeBase):
    pass


class Workload(Base):
    __tablename__ = "workloads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ipa_principal: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    workload_type: Mapped[WorkloadType] = mapped_column(SAEnum(WorkloadType), nullable=False)
    current_state: Mapped[WorkloadState] = mapped_column(
        SAEnum(WorkloadState), nullable=False, default=WorkloadState.REGISTERED
    )
    backend_types: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False)
    stale_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    attestation_records: Mapped[list["AttestationRecord"]] = relationship(back_populates="workload")
    state_transitions: Mapped[list["StateTransition"]] = relationship(back_populates="workload")


class AttestationRecord(Base):
    __tablename__ = "attestation_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workloads.id"), nullable=False)
    backend: Mapped[BackendType] = mapped_column(SAEnum(BackendType), nullable=False)
    verdict: Mapped[AttestationVerdict] = mapped_column(SAEnum(AttestationVerdict), nullable=False)
    evidence_hash: Mapped[str | None] = mapped_column(String(128))
    policy_hash: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    rekor_entry_uuid: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    workload: Mapped["Workload"] = relationship(back_populates="attestation_records")

    __table_args__ = (Index("idx_attest_workload", "workload_id", "created_at"),)


class StateTransition(Base):
    __tablename__ = "state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workloads.id"), nullable=False)
    from_state: Mapped[WorkloadState] = mapped_column(SAEnum(WorkloadState), nullable=False)
    to_state: Mapped[WorkloadState] = mapped_column(SAEnum(WorkloadState), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    rekor_entry_uuid: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    workload: Mapped["Workload"] = relationship(back_populates="state_transitions")

    __table_args__ = (Index("idx_transitions_workload", "workload_id", "created_at"),)


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    policy_type: Mapped[str] = mapped_column(String(50), nullable=False, default="simple")
    policy_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scope: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_actor", "actor"),
    )


class KBSSecret(Base):
    __tablename__ = "kbs_secrets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(255), nullable=False)
    tag: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    required_state: Mapped[WorkloadState] = mapped_column(
        SAEnum(WorkloadState), nullable=False, default=WorkloadState.HEALTHY
    )
    workload_scope: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("repo", "secret_type", "tag"),)


# Create async engine
engine = create_async_engine(settings.database_url, echo=False)

# Create session factory
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes to get DB session."""
    async with async_session() as session:
        yield session
