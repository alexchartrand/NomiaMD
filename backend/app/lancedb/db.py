from typing import List
from lancedb import DBConnection
from app.lancedb.models import CodeRow
from abc import ABC, abstractmethod
from pydantic import BaseModel

CODES_TABLE_NAME = "codes"

class ITableReader(ABC):
    @abstractmethod
    def get(self, id: str) -> BaseModel:
        pass
    @abstractmethod
    def get_all(self, ids: list[str]) -> List[BaseModel]:
        pass

class CodeTable(ITableReader):

    def __init__(self, db: DBConnection):
        self._table = db.open_table(CODES_TABLE_NAME)

    def get(self, id: str) -> CodeRow:
        quoted = "'" + id.replace("'", "''") + "'"
        rows = self._table.search().where(f"number = {quoted}").to_list()

        if len(rows) != 1:
            raise ValueError(f"Expected exactly one code row for number={id!r}, found {len(rows)}")

        return CodeRow.model_validate(rows[0])

    def get_all(self, ids: list[str]) -> List[CodeRow]:
        # Quote-escape rather than trust code numbers are always digit-only, since they come
        # from a retrieved embedding hit rather than a hardcoded source.
        quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in ids)
        rows = self._table.search().where(f"number IN ({quoted})").to_list()
        return [CodeRow.model_validate(row) for row in rows]