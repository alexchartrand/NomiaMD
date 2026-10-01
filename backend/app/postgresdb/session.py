"""Transaction boundaries. Repositories (repositories/) never open, commit or roll back a
session themselves — they're handed one and only `flush()`, so several repositories (and
the service composing them) share one atomic unit of work. Whoever opens the session owns
its outcome: `session_scope` commits when its block exits normally and rolls back when it
raises.

An HTTP request gets one such scope through app/postgresdb/dependencies.py's `DbSession`;
scripts and long-running flows that must not hold a pooled connection across slow I/O (the
LLM calls in /extract — see app/extraction/router.py) open short scopes directly.

Sessions come from the `PostgresDB` bound by `bind_database` — app/bootstrap.py's
`postgres_database()` does that once at startup, same pattern as the task registry's
`init_tasks`."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.postgresdb.database import PostgresDB


class DatabaseNotOpenError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "No database bound — app/bootstrap.py's postgres_database() (or "
            "application_services()) must run before any session_scope()"
        )


_database: PostgresDB | None = None


def bind_database(database: PostgresDB | None) -> None:
    global _database
    _database = database


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    if _database is None:
        raise DatabaseNotOpenError()
    async with _database.sessionmaker() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        await session.commit()
