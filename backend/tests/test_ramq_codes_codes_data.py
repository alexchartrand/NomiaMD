"""Tests for app/ramq_codes/codes_data.py — CodesData is a thin join: pass candidate numbers
to an ITableReader, run whatever rows come back through an IConverter. Both collaborators
are fakes here so this only pins CodesData's own wiring, not CodeTable/CodesRowConverter
(covered separately in tests/test_lancedb_db.py and tests/test_lancedb_converter.py)."""

from app.lancedb.db import ITableReader
from app.lancedb.converter import IConverter
from app.ramq_codes.codes_data import CodesData
from app.ramq_codes.models import Code


class _FakeTableReader(ITableReader):
    def __init__(self, rows_by_number: dict[str, object]):
        self._rows_by_number = rows_by_number
        self.get_all_calls: list[list[str]] = []

    async def get(self, id: str):
        return self._rows_by_number[id]

    async def get_all(self, ids: list[str]) -> list:
        self.get_all_calls.append(list(ids))
        return [self._rows_by_number[i] for i in ids if i in self._rows_by_number]


class _FakeConverter(IConverter):
    """Converts a raw "row" (here, just a dict) into a Code by copying number/description
    straight across — enough to prove CodesData routes every returned row through the
    converter, without needing a real CodeRow."""

    def __init__(self):
        self.converted: list[object] = []

    def convert(self, data: dict) -> Code:
        self.converted.append(data)
        return Code(number=data["number"], description=data["description"], confidence=1.0)


async def test_get_converts_every_row_the_table_returns():
    table = _FakeTableReader({"A": {"number": "A", "description": "desc A"}, "B": {"number": "B", "description": "desc B"}})
    converter = _FakeConverter()
    codes_data = CodesData(table, converter)

    result = await codes_data.get(["A", "B"])

    assert [c.number for c in result] == ["A", "B"]
    assert [c.description for c in result] == ["desc A", "desc B"]


async def test_get_passes_requested_numbers_through_to_the_table_unchanged():
    table = _FakeTableReader({"A": {"number": "A", "description": ""}})
    codes_data = CodesData(table, _FakeConverter())

    await codes_data.get(["A", "Z"])

    assert table.get_all_calls == [["A", "Z"]]


async def test_get_only_converts_rows_the_table_actually_returned():
    # A requested number the table couldn't resolve (stale candidate) is simply absent from
    # the table's result — CodesData doesn't call the converter for it.
    table = _FakeTableReader({"A": {"number": "A", "description": ""}})
    converter = _FakeConverter()
    codes_data = CodesData(table, converter)

    result = await codes_data.get(["A", "MISSING"])

    assert [c.number for c in result] == ["A"]
    assert len(converter.converted) == 1


async def test_get_with_no_numbers_returns_no_codes():
    table = _FakeTableReader({})
    codes_data = CodesData(table, _FakeConverter())

    assert await codes_data.get([]) == []
