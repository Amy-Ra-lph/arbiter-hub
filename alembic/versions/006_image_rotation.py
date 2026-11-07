"""Add image rotation support: artifact columns and ROTATING state

Revision ID: 006
Revises: 005
Create Date: 2026-10-20 17:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workloads", sa.Column("artifact_ref", sa.String(2048), nullable=True))
    op.add_column("workloads", sa.Column("artifact_digest", sa.String(128), nullable=True))
    op.add_column("workloads", sa.Column("previous_artifact_digest", sa.String(128), nullable=True))

    op.execute("ALTER TYPE workloadstate ADD VALUE IF NOT EXISTS 'rotating'")


def downgrade() -> None:
    op.drop_column("workloads", "previous_artifact_digest")
    op.drop_column("workloads", "artifact_digest")
    op.drop_column("workloads", "artifact_ref")
