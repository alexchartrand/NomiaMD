"""Async SQLAlchemy engine/session setup.

Defaults to a local SQLite file so the pipeline runs with zero setup. Point DATABASE_URL at
a real Postgres instance for anything beyond local development — nothing else needs to
change (SQLAlchemy handles the dialect difference). Async throughout: psycopg3 (the driver
implied by DATABASE_URL's `postgresql+psycopg://` convention) has native asyncio support
under that same dialect string, and aiosqlite backs the SQLite default.
"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

DATABASE_URL = settings.database_url
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # A long-lived container against a Postgres that recycles/drops idle connections would
    # otherwise be handed a stale one from the pool; pool_pre_ping pings before reuse.
    # Meaningless (and unsupported by aiosqlite's NullPool) on the SQLite dev path.
    **({} if _is_sqlite else {"pool_pre_ping": True, "pool_size": 10}),
)

if _is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        # SQLite ignores every FK (and its ondelete CASCADE/RESTRICT/SET NULL) unless this
        # is set on each new connection — without it, dev and the test suite would never
        # exercise the constraints Postgres enforces in prod.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
