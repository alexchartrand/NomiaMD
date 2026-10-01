"""FastAPI glue for session.py: one session, and one transaction, per request.

`scope="function"` ends the dependency — commit or rollback — right after the path
operation returns and *before* the response is sent, so a commit that fails surfaces as a
500 rather than after the client already got a 2xx. Every dependency in a request that asks
for `DbSession` gets the same session (FastAPI caches a dependency per request)."""

from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.postgresdb.session import session_scope


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
