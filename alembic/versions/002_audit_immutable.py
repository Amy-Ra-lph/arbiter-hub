"""append-only audit log triggers

Revision ID: 002
Revises: 001
Create Date: 2026-10-18 16:00:00.000000

"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
    """)
    op.execute("""
        CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation()")
