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

from app.code_catalog import init_code_catalog
from app.config import settings
from app.intake.connectors.epic_fhir.factory import check_sandbox_startup
from app.lancedb import CodeRepository, DocumentRepository, LanceDB
from app.llm import EmbeddingDimensionGuard, chat_provider, embedding_provider, get_embedding_client
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
    # An unknown LLM_PROVIDER/EMBEDDING_PROVIDER fails the boot, not the first extraction.
    chat_provider()
    embedding_provider()
    check_sandbox_startup(settings)
    async with postgres_database():
        db = await LanceDB.open()
        try:
            # Query vectors must live in the same space as the stored ones; a mismatch would
            # otherwise silently degrade hybrid search to its FTS half.
            await EmbeddingDimensionGuard(get_embedding_client()).check(await db.vector_dimensions())
            codes = CodeRepository(db.code_tables)
            documents = DocumentRepository(db.documents_table)
            init_tasks(codes=codes)
            init_code_catalog(codes)
            init_ramq_query_engine(codes, documents)
            yield db
        finally:
            db.close()
