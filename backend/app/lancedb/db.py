from typing import Awaitable, Callable, List
from lancedb import AsyncConnection, AsyncTable
from app.lancedb.models import CodeRow
from abc import ABC, abstractmethod
from pydantic import BaseModel

CODES_TABLE_NAME = "codes"

class ITableReader(ABC):
    @abstractmethod
    async def get(self, id: str) -> BaseModel:
        pass
    @abstractmethod
    async def get_all(self, ids: list[str]) -> List[BaseModel]:
        pass

class CodeTable(ITableReader):

    def __init__(self, get_db: Callable[[], Awaitable[AsyncConnection]]):
        self._get_db = get_db
        self._table: AsyncTable | None = None

    async def _open_table(self) -> AsyncTable:
        # Deferred rather than opened at construction: the async lancedb connection can only
        # be established inside a running event loop, but get_db is handed to CodeTable at
        # process-startup import time (app/tasks/registry.py), before one exists.
        if self._table is None:
            db = await self._get_db()
            self._table = await db.open_table(CODES_TABLE_NAME)
        return self._table

    async def get(self, id: str) -> CodeRow:
        quoted = "'" + id.replace("'", "''") + "'"
        table = await self._open_table()
        rows = await table.query().where(f"number = {quoted}").to_list()

        if len(rows) != 1:
            raise ValueError(f"Expected exactly one code row for number={id!r}, found {len(rows)}")

        return CodeRow.model_validate(rows[0])

    async def get_all(self, ids: list[str]) -> List[CodeRow]:
        # Quote-escape rather than trust code numbers are always digit-only, since they come
        # from a retrieved embedding hit rather than a hardcoded source.
        quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in ids)
        table = await self._open_table()
        rows = await table.query().where(f"number IN ({quoted})").to_list()
        return [CodeRow.model_validate(row) for row in rows]