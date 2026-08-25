"""Connection wiring for the RAMQ LanceDB at DB_PATH. Mirrors app/postgresdb/database.py:
that module builds its engine/sessionmaker at import time (sync, no I/O); LanceDB.open()
can't be built at import time the same way, because lancedb.connect_async needs a running
event loop — so this is opened explicitly by the app lifespan (app/bootstrap.py) instead.
"""

import lancedb
from lancedb import AsyncConnection
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.config import settings
from app.lancedb.repository import CodeRepository

CODES_TABLE_NAME = "codes"
EMBEDDINGS_TABLE_NAME = "code-embeddings"


class LanceDB:
    """Open handle on the RAMQ LanceDB at DB_PATH. Opened once by the app lifespan
    (app/bootstrap.py's application_services()), closed on shutdown; hands out the
    repositories and the llama_index vector store built over the same database."""

    def __init__(self, connection: AsyncConnection, codes: CodeRepository, vector_store: LanceDBVectorStore) -> None:
        self._connection = connection
        self._codes = codes
        self._vector_store = vector_store

    @classmethod
    async def open(cls) -> "LanceDB":
        connection = await lancedb.connect_async(settings.db_path)
        codes = CodeRepository(await connection.open_table(CODES_TABLE_NAME))
        vector_store = LanceDBVectorStore(
            uri=settings.db_path, table_name=EMBEDDINGS_TABLE_NAME, flat_metadata=False
        )
        return cls(connection, codes, vector_store)

    @property
    def codes(self) -> CodeRepository:
        return self._codes

    @property
    def vector_store(self) -> LanceDBVectorStore:
        return self._vector_store

    def close(self) -> None:
        # lancedb 0.37's AsyncConnection.close() is sync, not a coroutine.
        self._connection.close()
