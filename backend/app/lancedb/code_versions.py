"""Resolves which `codes_<rev>` table is current. ramq-ingestion writes one codes table per
manual revision and keeps older ones for reference; its small `code_versions` registry marks
the one to retrieve from (exactly one row with is_current=True, flipped in a single commit
when a new manual is promoted — see its code_version_registry.py).

The table name is always read from the registry row, never rebuilt from a revision string:
only ramq-ingestion knows the naming scheme."""

from abc import ABC, abstractmethod

from lancedb import AsyncConnection, AsyncTable

from app.lancedb.models import CodeVersionRow


class NoCurrentCodesTableError(RuntimeError):
    """The `code_versions` registry doesn't name exactly one current codes table. Raised
    rather than falling back to any table: retrieving from the wrong manual revision would
    silently suggest codes (and fees) that aren't in force."""


class ICodeTableProvider(ABC):
    @abstractmethod
    async def current(self) -> AsyncTable:
        pass

    @abstractmethod
    async def current_version(self) -> CodeVersionRow:
        pass


class CurrentCodeTableProvider(ICodeTableProvider):
    """Re-reads the registry on every call, so a promote takes effect without a restart. The
    registry is a one-row-per-revision local table, so the read costs next to nothing; how
    quickly a promote becomes visible is bounded by the connection's
    read_consistency_interval (see database.py), not by any cache here.

    Opened table handles are cached by name — opening is the expensive part, and a
    promoted table keeps its name for as long as it exists."""

    def __init__(self, connection: AsyncConnection, registry_table: AsyncTable):
        self._connection = connection
        self._registry_table = registry_table
        self._tables: dict[str, AsyncTable] = {}

    async def current(self) -> AsyncTable:
        version = await self.current_version()
        table = self._tables.get(version.table_name)
        if table is None:
            table = await self._connection.open_table(version.table_name)
            self._tables[version.table_name] = table
        return table

    async def current_version(self) -> CodeVersionRow:
        rows = await self._registry_table.query().where("is_current").to_list()
        if len(rows) != 1:
            raise NoCurrentCodesTableError(
                f"Expected exactly one current row in the code_versions registry, found {len(rows)}"
            )
        return CodeVersionRow.model_validate(rows[0])


class UnknownCodesTableError(LookupError):
    """A pinned table name has no row in the `code_versions` registry."""


class PinnedCodeTableProvider(ICodeTableProvider):
    """Always the same registered codes table, whether current or not — for evaluating a
    table ramq-ingestion built but hasn't promoted (one re-embedded with a candidate
    embedding model, say) without touching what production reads. Only the benchmark uses
    it."""

    def __init__(self, connection: AsyncConnection, registry_table: AsyncTable, table_name: str):
        self._connection = connection
        self._registry_table = registry_table
        self._table_name = table_name
        self._table: AsyncTable | None = None

    async def current(self) -> AsyncTable:
        if self._table is None:
            await self.current_version()
            self._table = await self._connection.open_table(self._table_name)
        return self._table

    async def current_version(self) -> CodeVersionRow:
        quoted = self._table_name.replace("'", "''")
        rows = await self._registry_table.query().where(f"table_name = '{quoted}'").to_list()
        if len(rows) != 1:
            raise UnknownCodesTableError(
                f"{self._table_name!r} is not registered in code_versions (found {len(rows)} rows)"
            )
        return CodeVersionRow.model_validate(rows[0])
