"""Read access to the LanceDB tables in models.py — one repository class per table, each
owning its own query building and row validation. Mirrors app/postgresdb/repository.py;
the connection wiring lives in database.py."""

import logging
from abc import ABC, abstractmethod
from typing import List

from lancedb import AsyncTable

from app.lancedb.models import CodeRow

logger = logging.getLogger(__name__)


class ICodeRepository(ABC):
    @abstractmethod
    async def get_by_number(self, number: str) -> CodeRow:
        pass

    @abstractmethod
    async def list_by_numbers(self, numbers: List[str]) -> List[CodeRow]:
        pass


class CodeRepository(ICodeRepository):
    """Handed an already-open table by LanceDB.open() (database.py) — the async lancedb
    connection is established once at startup, never on a query."""

    def __init__(self, table: AsyncTable):
        self._table = table

    async def get_by_number(self, number: str) -> CodeRow:
        quoted = "'" + number.replace("'", "''") + "'"
        rows = await self._table.query().where(f"number = {quoted}").to_list()

        if len(rows) != 1:
            raise ValueError(f"Expected exactly one code row for number={number!r}, found {len(rows)}")

        return CodeRow.model_validate(rows[0])

    async def list_by_numbers(self, numbers: List[str]) -> List[CodeRow]:
        # Quote-escape rather than trust code numbers are always digit-only, since they come
        # from a retrieved embedding hit rather than a hardcoded source.
        quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in numbers)
        rows = await self._table.query().where(f"number IN ({quoted})").to_list()
        results = [CodeRow.model_validate(row) for row in rows]

        missing = sorted(set(numbers) - {r.number for r in results})
        if missing:
            logger.warning(
                "Candidate RAMQ code number(s) not found in the codes table (stale "
                "embeddings index?) — dropped from results",
                extra={"missing_numbers": missing},
            )

        return results
