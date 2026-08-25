"""The process's single composition root: opens the RAMQ LanceDB and wires everything built
on top of it (the extraction task registry, the RAMQ chatbot engine). Used by app/main.py's
FastAPI lifespan and by the real-API scripts (try_extraction.py, eval_extraction.py) that
run the extraction pipeline outside FastAPI.

Deferred to here, rather than done at import time, because lancedb.connect_async needs a
running event loop — see app/lancedb/database.py's LanceDB.open()."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.lancedb import LanceDB

# app.tasks.registry must be imported before app.ramq_chatbot: both eventually import
# app.lancedb.converter, which itself imports app.ramq_codes.models — importing
# app.ramq_chatbot first would touch app.lancedb.converter while app.ramq_codes is still
# mid-import (via app.tasks.registry -> app.ramq_codes -> .task -> .codes_data ->
# app.lancedb.converter), causing a circular-import ImportError. Importing app.ramq_codes
# to completion first (via this line) avoids that.
from app.tasks.registry import init_tasks
from app.ramq_chatbot import init_ramq_query_engine


@asynccontextmanager
async def application_services() -> AsyncIterator[LanceDB]:
    db = await LanceDB.open()
    try:
        init_tasks(db)
        init_ramq_query_engine(db.codes)
        yield db
    finally:
        db.close()
