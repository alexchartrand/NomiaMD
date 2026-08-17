from typing import List

from app.lancedb.converter import IConverter
from app.lancedb.db import ITableReader
from app.ramq_codes.models import Code

class CodesData:

    def __init__(self, table: ITableReader, converter: IConverter) -> None:
        self._table = table
        self._converter = converter

    async def get(self, numbers: List[str]) -> List[Code]:
        codes = await self._table.get_all(numbers)
        return [self._converter.convert(code) for code in codes]

