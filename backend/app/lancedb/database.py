"""Connection wiring for the RAMQ LanceDB at DB_PATH. Mirrors app/postgresdb/database.py:
that module builds its engine/sessionmaker at import time (sync, no I/O); LanceDB.open()
can't be built at import time the same way, because lancedb.connect_async needs a running
event loop — so this is opened explicitly by the app lifespan (app/bootstrap.py) instead.
"""

from datetime import timedelta

import lancedb
import pyarrow as pa
from lancedb import AsyncConnection, AsyncTable

from app.config import settings
from app.lancedb.code_versions import CurrentCodeTableProvider, ICodeTableProvider, PinnedCodeTableProvider

CODE_VERSIONS_TABLE_NAME = "code_versions"
DOCUMENTS_TABLE_NAME = "documents-embeddings"
VECTOR_COLUMN = "vector"

# How stale an already-open table may be before LanceDB re-checks it for a newer version.
# Without it, an open table never sees later writes: a promote (the `code_versions` flip),
# an in-place re-extraction of the current codes table, or a rebuilt documents table would
# all need a restart to show up.
READ_CONSISTENCY_INTERVAL = timedelta(seconds=30)


class LanceDB:
    """Open handle on the RAMQ LanceDB at DB_PATH. Opened once by the app lifespan
    (app/bootstrap.py's application_services()), closed on shutdown; hands out the raw
    `documents-embeddings` table and a provider for the current `codes_<rev>` table (see
    code_versions.py — which codes table is current can change while the process runs).
    Connection wiring only — has no notion of app/lancedb/repository.py's repository
    classes; those are built by the composition root (app/bootstrap.py) from what's exposed
    here.

    Every table lives in the same LanceDB directory (ramq-ingestion writes them together),
    so one AsyncConnection serves all of them."""

    def __init__(
        self,
        connection: AsyncConnection,
        code_tables: ICodeTableProvider,
        documents_table: AsyncTable,
        registry_table: AsyncTable,
    ) -> None:
        self._connection = connection
        self._code_tables = code_tables
        self._documents_table = documents_table
        self._registry_table = registry_table

    @classmethod
    async def open(cls) -> "LanceDB":
        connection = await lancedb.connect_async(
            settings.db_path, read_consistency_interval=READ_CONSISTENCY_INTERVAL
        )
        try:
            registry_table = await connection.open_table(CODE_VERSIONS_TABLE_NAME)
            code_tables = CurrentCodeTableProvider(connection, registry_table)
            # Resolved once here so a DB with no current codes table fails at startup, not on
            # the first extraction.
            await code_tables.current()
            documents_table = await connection.open_table(DOCUMENTS_TABLE_NAME)
        except Exception:
            connection.close()
            raise

        return cls(connection, code_tables, documents_table, registry_table)

    @property
    def code_tables(self) -> ICodeTableProvider:
        return self._code_tables

    def pinned_code_tables(self, table_name: str) -> PinnedCodeTableProvider:
        """A provider fixed on one registered `codes_<rev>` table, current or not (the
        benchmark's --codes-table)."""
        return PinnedCodeTableProvider(self._connection, self._registry_table, table_name)

    @property
    def documents_table(self) -> AsyncTable:
        return self._documents_table

    async def vector_dimensions(self) -> dict[str, int]:
        """Each embedded table's name mapped to its vector column's fixed dimension — the
        current codes table and the documents table. app/bootstrap.py compares these with
        the query embedding model's output at startup."""
        version = await self._code_tables.current_version()
        return {
            version.table_name: await vector_dimension(await self._code_tables.current()),
            DOCUMENTS_TABLE_NAME: await vector_dimension(self._documents_table),
        }

    def close(self) -> None:
        # lancedb 0.37's AsyncConnection.close() is sync, not a coroutine.
        self._connection.close()


async def vector_dimension(table: AsyncTable) -> int:
    """The fixed size of `table`'s vector column (ramq-ingestion writes it as a
    fixed_size_list<float32>)."""
    vector_type = (await table.schema()).field(VECTOR_COLUMN).type
    if not pa.types.is_fixed_size_list(vector_type):
        raise TypeError(f"{table.name}.{VECTOR_COLUMN} is {vector_type}, expected a fixed-size list")
    return vector_type.list_size
