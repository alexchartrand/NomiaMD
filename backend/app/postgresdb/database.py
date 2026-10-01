"""Async SQLAlchemy engine setup.

Defaults to a local SQLite file so the pipeline runs with zero setup. Point DATABASE_URL at
a real Postgres instance for anything beyond local development — nothing else needs to
change (SQLAlchemy handles the dialect difference). Async throughout: psycopg3 (the driver
implied by DATABASE_URL's `postgresql+psycopg://` convention) has native asyncio support
under that same dialect string, and aiosqlite backs the SQLite default.

Nothing is built at import time: `PostgresDB.open()` is called from app/bootstrap.py (the
process's single composition root, mirroring app/lancedb/database.py's `LanceDB.open()`),
so which database a process talks to is decided when it starts, not by whatever
DATABASE_URL happened to be set when this module was first imported.
"""

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    # Read server-generated columns (created_at, updated_at, generated_at) back in the same
    # INSERT/UPDATE statement via RETURNING, so they're populated after a flush — an async
    # session can't lazy-load an expired attribute later.
    __mapper_args__ = {"eager_defaults": True}


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    # SQLite ignores every FK (and its ondelete CASCADE/RESTRICT/SET NULL) unless this is
    # set on each new connection — without it, dev and the test suite would never exercise
    # the constraints Postgres enforces in prod.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _create_engine(url: str) -> AsyncEngine:
    is_sqlite = url.startswith("sqlite")
    engine = create_async_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        # A long-lived container against a Postgres that recycles/drops idle connections
        # would otherwise be handed a stale one from the pool; pool_pre_ping pings before
        # reuse. Meaningless (and unsupported by aiosqlite's NullPool) on the SQLite dev path.
        **({} if is_sqlite else {"pool_pre_ping": True, "pool_size": 10}),
    )
    if is_sqlite:
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


class PostgresDB:
    """One engine and the session factory over it. Opened once per process by
    app/bootstrap.py and disposed on shutdown; app/postgresdb/session.py's `session_scope`
    hands out sessions from whichever instance was bound there."""

    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        # expire_on_commit=False: a User loaded in get_current_user's short scope must stay
        # readable after that scope commits (app/auth/dependencies.py).
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )

    @classmethod
    async def open(cls, url: str | None = None) -> "PostgresDB":
        db = cls(_create_engine(url or settings.database_url))
        await db._create_missing_tables()
        return db

    async def _create_missing_tables(self) -> None:
        # create_all never alters an existing table: until the first release, a schema change
        # means deleting the DB and letting this recreate it (see BACKLOG.md's "No Alembic").
        async with self._engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                # For patients' trigram name-search index (models.py). A trusted extension
                # since Postgres 13, so the database owner can create it.
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()
