from typing import List

from app.lancedb.converter import IConverter
from app.lancedb.repository import ICodeRepository
from app.ramq_codes.models import Code

class CodesData:

    def __init__(self, repository: ICodeRepository, converter: IConverter) -> None:
        self._repository = repository
        self._converter = converter

    async def get(self, numbers: List[str]) -> List[Code]:
        codes = await self._repository.list_by_numbers(numbers)
        return [self._converter.convert(code) for code in codes]
