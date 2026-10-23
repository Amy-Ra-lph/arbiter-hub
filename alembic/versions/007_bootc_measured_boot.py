"""add BOOTC workload type and MEASURED_BOOT backend type

Revision ID: 007
Revises: 006
Create Date: 2026-10-21 23:30:00.000000

"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE workloadtype ADD VALUE IF NOT EXISTS 'BOOTC'")
    op.execute("ALTER TYPE backendtype ADD VALUE IF NOT EXISTS 'MEASURED_BOOT'")


def downgrade() -> None:
    pass
