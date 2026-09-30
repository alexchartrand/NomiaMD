"""Transaction boundaries. Repositories (repositories/) never open, commit or roll back a
session themselves — they're handed one and only `flush()`, so several repositories (and
the service composing them) share one atomic unit of work. Whoever opens the session owns
its outcome: `session_scope` commits when its block exits normally and rolls back when it
raises.

An HTTP request gets one such scope through app/postgresdb/dependencies.py's `DbSession`;
scripts and long-running flows that must not hold a pooled connection across slow I/O (the
LLM calls in /extract — see app/extraction/router.py) open short scopes directly."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.postgresdb.database import async_session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        await session.commit()
