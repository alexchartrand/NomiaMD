import asyncio
from functools import cache

import lancedb
from lancedb import AsyncConnection
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from app.config import settings
from app.lancedb.db import CodeTable

EMBEDDINGS_TABLE_NAME = "code-embeddings"

db_dir = settings.db_path

_db: AsyncConnection | None = None
_db_lock = asyncio.Lock()


async def get_database() -> AsyncConnection:
    global _db
    if _db is None:
        async with _db_lock:
            if _db is None:
                _db = await lancedb.connect_async(db_dir)
    return _db

@cache
def get_vectorstore():
    return LanceDBVectorStore(uri=db_dir, table_name=EMBEDDINGS_TABLE_NAME, flat_metadata=False)

@cache
def get_codes_table_reader():
    return CodeTable(get_database)
