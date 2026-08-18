"""Storage for extraction runs.

Defaults to a local SQLite file so the pipeline runs with zero setup. Point DATABASE_URL at
a real Postgres instance for anything beyond local development — nothing else in this file
needs to change (SQLAlchemy handles the dialect difference). Async throughout: psycopg3
(the driver implied by DATABASE_URL's `postgresql+psycopg://` convention) has native asyncio
support under that same dialect string, and aiosqlite backs the SQLite default.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL, connect_args=(
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
))
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class ExtractionRecord(Base):
    """One stored extraction run. `transcript` is kept only long enough for physician
    review — set up a retention/purge job before this holds real patient data; see the
    compliance note in the top-level README."""

    __tablename__ = "extraction_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(64))
    transcript: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_extraction(
    *, task: str, transcript: str, result: dict, model: str, source_system: str | None
) -> ExtractionRecord:
    async with async_session() as session:
        record = ExtractionRecord(
            task=task,
            transcript=transcript,
            result_json=json.dumps(result),
            model=model,
            source_system=source_system,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record
