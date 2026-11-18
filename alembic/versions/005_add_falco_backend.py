"""add FALCO to backendtype enum

Revision ID: 005
Revises: 004
Create Date: 2026-10-20 15:10:00.000000

"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE backendtype ADD VALUE IF NOT EXISTS 'FALCO'")


def downgrade() -> None:
    pass
