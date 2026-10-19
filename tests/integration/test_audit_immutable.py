import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.models.db import AuditLog, Base

TEST_DB_URL = os.environ.get(
    "ARBITER_DATABASE_URL",
    "postgresql+asyncpg://arbiter:arbiter@localhost:5432/arbiter_test",
)

TRIGGER_FUNC = (
    "CREATE OR REPLACE FUNCTION prevent_audit_mutation() "
    "RETURNS TRIGGER AS "
    "'BEGIN RAISE EXCEPTION ''audit_log is append-only: % not permitted'', TG_OP; END;' "
    "LANGUAGE plpgsql"
)

TRIGGER_UPDATE = (
    "CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log "
    "FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()"
)

TRIGGER_DELETE = (
    "CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log "
    "FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()"
)


async def _apply_triggers(conn):
    await conn.execute(text("DROP TRIGGER IF EXISTS audit_no_delete ON audit_log"))
    await conn.execute(text("DROP TRIGGER IF EXISTS audit_no_update ON audit_log"))
    await conn.execute(text("DROP FUNCTION IF EXISTS prevent_audit_mutation()"))
    await conn.execute(text(TRIGGER_FUNC))
    await conn.execute(text(TRIGGER_UPDATE))
    await conn.execute(text(TRIGGER_DELETE))


async def _drop_triggers(conn):
    await conn.execute(text("DROP TRIGGER IF EXISTS audit_no_delete ON audit_log"))
    await conn.execute(text("DROP TRIGGER IF EXISTS audit_no_update ON audit_log"))
    await conn.execute(text("DROP FUNCTION IF EXISTS prevent_audit_mutation()"))


@pytest.fixture
async def audit_session():
    eng = create_async_engine(TEST_DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with eng.begin() as conn:
        await _apply_triggers(conn)

    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

    async with eng.begin() as conn:
        await _drop_triggers(conn)
    await eng.dispose()


def _make_audit_row():
    return AuditLog(
        id=uuid.uuid4(),
        actor="test@EXAMPLE.COM",
        actor_type="admin",
        action="test_action",
        target_type="workload",
        target_id=uuid.uuid4(),
        detail={},
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_audit_insert_succeeds(audit_session):
    row = _make_audit_row()
    audit_session.add(row)
    await audit_session.commit()
    result = await audit_session.get(AuditLog, row.id)
    assert result is not None
    assert result.actor == "test@EXAMPLE.COM"


@pytest.mark.asyncio
async def test_audit_update_blocked(audit_session):
    row = _make_audit_row()
    audit_session.add(row)
    await audit_session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await audit_session.execute(
            text("UPDATE audit_log SET actor = 'tampered' WHERE id = :id"),
            {"id": str(row.id)},
        )


@pytest.mark.asyncio
async def test_audit_delete_blocked(audit_session):
    row = _make_audit_row()
    audit_session.add(row)
    await audit_session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await audit_session.execute(
            text("DELETE FROM audit_log WHERE id = :id"),
            {"id": str(row.id)},
        )
