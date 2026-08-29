"""Connection wiring for the RAMQ LanceDB at DB_PATH. Mirrors app/postgresdb/database.py:
that module builds its engine/sessionmaker at import time (sync, no I/O); LanceDB.open()
can't be built at import time the same way, because lancedb.connect_async needs a running
event loop — so this is opened explicitly by the app lifespan (app/bootstrap.py) instead.
"""

import lancedb
from lancedb import AsyncConnection, AsyncTable
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.config import settings

CODES_TABLE_NAME = "codes"
EMBEDDINGS_TABLE_NAME = "code-embeddings"
DOCUMENTS_TABLE_NAME = "documents-embeddings"


class LanceDB:
    """Open handle on the RAMQ LanceDB. Opened once by the app lifespan
    (app/bootstrap.py's application_services()), closed on shutdown; hands out the raw
    tables and the llama_index vector store built over the same database(s). Connection
    wiring only — has no notion of app/lancedb/repository.py's repository classes; those
    are built by the composition root (app/bootstrap.py) from the tables exposed here.

    `documents-embeddings` lives at RAMQ_CHATBOT_DB_PATH — a directory distinct from
    `codes`/`code-embeddings`'s DB_PATH in deployment (see ramq-ingestion's
    scripts/deploy_db.sh) — so it gets its own AsyncConnection rather than reusing the one
    above. Owning both connections here (rather than app/ramq_chatbot/factory.py opening its
    own, as the old LanceDBVectorStore-based wiring did) keeps every LanceDB connection's
    lifetime tied to this single composition root."""

    def __init__(
        self,
        connection: AsyncConnection,
        codes_table: AsyncTable,
        vector_store: LanceDBVectorStore,
        documents_connection: AsyncConnection,
        documents_table: AsyncTable,
    ) -> None:
        self._connection = connection
        self._codes_table = codes_table
        self._vector_store = vector_store
        self._documents_connection = documents_connection
        self._documents_table = documents_table

    @classmethod
    async def open(cls) -> "LanceDB":
        connection = await lancedb.connect_async(settings.db_path)
        try:
            codes_table = await connection.open_table(CODES_TABLE_NAME)
            vector_store = LanceDBVectorStore(
                uri=settings.db_path, table_name=EMBEDDINGS_TABLE_NAME, flat_metadata=False
            )

            documents_connection = await lancedb.connect_async(settings.ramq_chatbot_db_path)
            try:
                documents_table = await documents_connection.open_table(DOCUMENTS_TABLE_NAME)
            except Exception:
                documents_connection.close()
                raise
        except Exception:
            connection.close()
            raise

        return cls(connection, codes_table, vector_store, documents_connection, documents_table)

    @property
    def codes_table(self) -> AsyncTable:
        return self._codes_table

    @property
    def vector_store(self) -> LanceDBVectorStore:
        return self._vector_store

    @property
    def documents_table(self) -> AsyncTable:
        return self._documents_table

    def close(self) -> None:
        # lancedb 0.37's AsyncConnection.close() is sync, not a coroutine.
        self._connection.close()
        self._documents_connection.close()
