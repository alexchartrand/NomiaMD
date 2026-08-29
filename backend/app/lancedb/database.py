"""Connection wiring for the RAMQ LanceDB at DB_PATH. Mirrors app/postgresdb/database.py:
that module builds its engine/sessionmaker at import time (sync, no I/O); LanceDB.open()
can't be built at import time the same way, because lancedb.connect_async needs a running
event loop — so this is opened explicitly by the app lifespan (app/bootstrap.py) instead.
"""

import lancedb
from lancedb import AsyncConnection, AsyncTable

from app.config import settings

CODES_TABLE_NAME = "codes"
DOCUMENTS_TABLE_NAME = "documents-embeddings"


class LanceDB:
    """Open handle on the RAMQ LanceDB at DB_PATH. Opened once by the app lifespan
    (app/bootstrap.py's application_services()), closed on shutdown; hands out the raw
    `codes`/`documents-embeddings` tables. Connection wiring only — has no notion of
    app/lancedb/repository.py's repository classes; those are built by the composition root
    (app/bootstrap.py) from the tables exposed here.

    Both tables live in the same LanceDB directory (ramq-ingestion writes them together —
    see its scripts/deploy_db.sh), so one AsyncConnection serves both."""

    def __init__(
        self,
        connection: AsyncConnection,
        codes_table: AsyncTable,
        documents_table: AsyncTable,
    ) -> None:
        self._connection = connection
        self._codes_table = codes_table
        self._documents_table = documents_table

    @classmethod
    async def open(cls) -> "LanceDB":
        connection = await lancedb.connect_async(settings.db_path)
        try:
            codes_table = await connection.open_table(CODES_TABLE_NAME)
            documents_table = await connection.open_table(DOCUMENTS_TABLE_NAME)
        except Exception:
            connection.close()
            raise

        return cls(connection, codes_table, documents_table)

    @property
    def codes_table(self) -> AsyncTable:
        return self._codes_table

    @property
    def documents_table(self) -> AsyncTable:
        return self._documents_table

    def close(self) -> None:
        # lancedb 0.37's AsyncConnection.close() is sync, not a coroutine.
        self._connection.close()
