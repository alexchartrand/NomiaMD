"""session_scope (app/postgresdb/session.py) owns the transaction outcome that repositories
leave to their caller: commit when its block exits normally, roll back when it raises."""

import uuid

import pytest

from app.postgresdb import DatabaseNotOpenError, UserRepository, UserRole, bind_database, session_scope


async def _find(email: str):
    async with session_scope() as session:
        return await UserRepository(session).get_by_email(email)


async def _create(session, email: str):
    await UserRepository(session).create(
        email=email, hashed_password="!", full_name="Dr. Scope", role=UserRole.PHYSICIAN
    )


async def test_block_that_exits_normally_is_committed():
    email = f"scope-{uuid.uuid4().hex[:8]}@example.test"

    async with session_scope() as session:
        await _create(session, email)

    assert await _find(email) is not None


async def test_block_that_raises_is_rolled_back():
    email = f"scope-{uuid.uuid4().hex[:8]}@example.test"

    with pytest.raises(RuntimeError):
        async with session_scope() as session:
            await _create(session, email)
            raise RuntimeError("fails after the write")

    assert await _find(email) is None


async def test_scope_before_any_database_is_bound_raises(postgres_db):
    bind_database(None)
    try:
        with pytest.raises(DatabaseNotOpenError):
            async with session_scope():
                pass
    finally:
        bind_database(postgres_db)
