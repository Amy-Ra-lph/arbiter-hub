"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-10-17 14:36:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workloads table
    op.create_table(
        "workloads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ipa_principal", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "workload_type",
            sa.Enum("agentic", "cvm", "service", name="workloadtype"),
            nullable=False,
        ),
        sa.Column(
            "current_state",
            sa.Enum(
                "registered",
                "attesting",
                "healthy",
                "stale",
                "failed",
                "under_remediation",
                "revoked",
                name="workloadstate",
            ),
            nullable=False,
        ),
        sa.Column(
            "backend_type",
            sa.Enum("keylime", "trustee", "cosign", "rekor", name="backendtype"),
            nullable=False,
        ),
        sa.Column("stale_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ipa_principal"),
    )

    # Create attestation_records table
    op.create_table(
        "attestation_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "backend",
            sa.Enum("keylime", "trustee", "cosign", "rekor", name="backendtype"),
            nullable=False,
        ),
        sa.Column(
            "verdict",
            sa.Enum("pass", "fail", "error", "unavailable", name="attestationverdict"),
            nullable=False,
        ),
        sa.Column("evidence_hash", sa.String(length=128), nullable=True),
        sa.Column("policy_hash", sa.String(length=128), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rekor_entry_uuid", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workload_id"], ["workloads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_attest_workload", "attestation_records", ["workload_id", "created_at"])

    # Create state_transitions table
    op.create_table(
        "state_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "from_state",
            sa.Enum(
                "registered",
                "attesting",
                "healthy",
                "stale",
                "failed",
                "under_remediation",
                "revoked",
                name="workloadstate",
            ),
            nullable=False,
        ),
        sa.Column(
            "to_state",
            sa.Enum(
                "registered",
                "attesting",
                "healthy",
                "stale",
                "failed",
                "under_remediation",
                "revoked",
                name="workloadstate",
            ),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.String(length=255), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("rekor_entry_uuid", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workload_id"], ["workloads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_transitions_workload", "state_transitions", ["workload_id", "created_at"])

    # Create policies table
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("policy_type", sa.String(length=50), nullable=False),
        sa.Column("policy_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_created", "audit_log", ["created_at"])
    op.create_index("idx_audit_actor", "audit_log", ["actor"])

    # Create kbs_secrets table
    op.create_table(
        "kbs_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo", sa.String(length=255), nullable=False),
        sa.Column("secret_type", sa.String(length=255), nullable=False),
        sa.Column("tag", sa.String(length=255), nullable=False),
        sa.Column("encrypted_value", sa.LargeBinary(), nullable=False),
        sa.Column(
            "required_state",
            sa.Enum(
                "registered",
                "attesting",
                "healthy",
                "stale",
                "failed",
                "under_remediation",
                "revoked",
                name="workloadstate",
            ),
            nullable=False,
        ),
        sa.Column("workload_scope", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo", "secret_type", "tag"),
    )


def downgrade() -> None:
    op.drop_table("kbs_secrets")
    op.drop_index("idx_audit_actor", table_name="audit_log")
    op.drop_index("idx_audit_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("policies")
    op.drop_index("idx_transitions_workload", table_name="state_transitions")
    op.drop_table("state_transitions")
    op.drop_index("idx_attest_workload", table_name="attestation_records")
    op.drop_table("attestation_records")
    op.drop_table("workloads")
    op.execute("DROP TYPE IF EXISTS backendtype")
    op.execute("DROP TYPE IF EXISTS attestationverdict")
    op.execute("DROP TYPE IF EXISTS workloadstate")
    op.execute("DROP TYPE IF EXISTS workloadtype")
