"""The process's single composition root: opens the relational database and the RAMQ
LanceDB, and wires everything built on top of them (the extraction task registry, the RAMQ
chatbot engine). Used by app/main.py's FastAPI lifespan and by the scripts — the real-API
ones (try_extraction.py, eval_extraction.py) take `application_services()`, the DB-only
ones (create_user.py, seed_db.py, reset_password.py) just `postgres_database()`.

Deferred to here, rather than done at import time, because lancedb.connect_async needs a
running event loop — see app/lancedb/database.py's LanceDB.open() — and so DATABASE_URL is
read when the process starts rather than when app.postgresdb is first imported."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.lancedb import CodeRepository, DocumentRepository, LanceDB
from app.postgresdb import PostgresDB, bind_database
from app.ramq_chatbot import init_ramq_query_engine
from app.tasks.registry import init_tasks


@asynccontextmanager
async def postgres_database(url: str | None = None) -> AsyncIterator[PostgresDB]:
    db = await PostgresDB.open(url)
    bind_database(db)
    try:
        yield db
    finally:
        bind_database(None)
        await db.close()


@asynccontextmanager
async def application_services() -> AsyncIterator[LanceDB]:
    async with postgres_database():
        db = await LanceDB.open()
        try:
            codes = CodeRepository(db.code_tables)
            documents = DocumentRepository(db.documents_table)
            init_tasks(codes=codes)
            init_ramq_query_engine(codes, documents)
            yield db
        finally:
            db.close()
