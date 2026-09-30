"""The process's single composition root: opens the RAMQ LanceDB and wires everything built
on top of it (the extraction task registry, the RAMQ chatbot engine). Used by app/main.py's
FastAPI lifespan and by the real-API scripts (try_extraction.py, eval_extraction.py) that
run the extraction pipeline outside FastAPI.

Deferred to here, rather than done at import time, because lancedb.connect_async needs a
running event loop — see app/lancedb/database.py's LanceDB.open()."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.lancedb import CodeRepository, DocumentRepository, LanceDB
from app.ramq_chatbot import init_ramq_query_engine
from app.tasks.registry import init_tasks


@asynccontextmanager
async def application_services() -> AsyncIterator[LanceDB]:
    db = await LanceDB.open()
    try:
        codes = CodeRepository(db.code_tables)
        documents = DocumentRepository(db.documents_table)
        init_tasks(codes=codes)
        init_ramq_query_engine(codes, documents)
        yield db
    finally:
        db.close()
