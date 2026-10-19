"""convert backend_type to backend_types array column

Revision ID: 003
Revises: 002
Create Date: 2026-10-19 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workloads",
        sa.Column("backend_types", sa.ARRAY(sa.String(50)), nullable=True),
    )
    op.execute("UPDATE workloads SET backend_types = ARRAY[backend_type::text]")
    op.alter_column("workloads", "backend_types", nullable=False)
    op.drop_column("workloads", "backend_type")


def downgrade() -> None:
    op.add_column(
        "workloads",
        sa.Column("backend_type", sa.VARCHAR(50), nullable=True),
    )
    op.execute("UPDATE workloads SET backend_type = backend_types[1]")
    op.alter_column("workloads", "backend_type", nullable=False)
    op.drop_column("workloads", "backend_types")
