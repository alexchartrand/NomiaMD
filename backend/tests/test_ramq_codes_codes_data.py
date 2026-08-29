"""Tests for app/ramq_codes/codes_data.py — CodesData is a thin join: pass candidate numbers
to an ICodeRepository, run whatever rows come back through an IConverter. Both collaborators
are fakes here so this only pins CodesData's own wiring, not CodeRepository/CodesRowConverter
(covered separately in tests/test_lancedb_repository.py and tests/test_lancedb_converter.py)."""

from app.lancedb.repository import ICodeRepository
from app.lancedb.converter import IConverter
from app.ramq_codes.codes_data import CodesData
from app.ramq_codes.models import Code


class _FakeCodeRepository(ICodeRepository):
    def __init__(self, rows_by_number: dict[str, object]):
        self._rows_by_number = rows_by_number
        self.list_by_numbers_calls: list[list[str]] = []

    async def get_by_number(self, number: str):
        return self._rows_by_number[number]

    async def list_by_numbers(self, numbers: list[str]) -> list:
        self.list_by_numbers_calls.append(list(numbers))
        return [self._rows_by_number[n] for n in numbers if n in self._rows_by_number]

    async def hybrid_search(self, text: str, vector: list[float], k: int) -> list:
        raise NotImplementedError("not exercised by CodesData")


class _FakeConverter(IConverter):
    """Converts a raw "row" (here, just a dict) into a Code by copying number/description
    straight across — enough to prove CodesData routes every returned row through the
    converter, without needing a real CodeRow."""

    def __init__(self):
        self.converted: list[object] = []

    def convert(self, data: dict) -> Code:
        self.converted.append(data)
        return Code(number=data["number"], libelle="", description=data["description"])


async def test_get_converts_every_row_the_table_returns():
    repository = _FakeCodeRepository({"A": {"number": "A", "description": "desc A"}, "B": {"number": "B", "description": "desc B"}})
    converter = _FakeConverter()
    codes_data = CodesData(repository, converter)

    result = await codes_data.get(["A", "B"])

    assert [c.number for c in result] == ["A", "B"]
    assert [c.description for c in result] == ["desc A", "desc B"]


async def test_get_passes_requested_numbers_through_to_the_table_unchanged():
    repository = _FakeCodeRepository({"A": {"number": "A", "description": ""}})
    codes_data = CodesData(repository, _FakeConverter())

    await codes_data.get(["A", "Z"])

    assert repository.list_by_numbers_calls == [["A", "Z"]]


async def test_get_only_converts_rows_the_table_actually_returned():
    # A requested number the table couldn't resolve (stale candidate) is simply absent from
    # the table's result — CodesData doesn't call the converter for it.
    repository = _FakeCodeRepository({"A": {"number": "A", "description": ""}})
    converter = _FakeConverter()
    codes_data = CodesData(repository, converter)

    result = await codes_data.get(["A", "MISSING"])

    assert [c.number for c in result] == ["A"]
    assert len(converter.converted) == 1


async def test_get_with_no_numbers_returns_no_codes():
    repository = _FakeCodeRepository({})
    codes_data = CodesData(repository, _FakeConverter())

    assert await codes_data.get([]) == []
