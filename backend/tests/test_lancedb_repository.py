"""Tests for app/lancedb/repository.py — ICodeRepository's ABC contract, and
CodeRepository's query building and row validation against a fake async lancedb table (no
real Lance dataset ever opened)."""

import re

import pytest

from app.lancedb.repository import CodeRepository, ICodeRepository
from app.lancedb.models import CodeRow


class _FakeSearchQuery:
    """Chainable stand-in for lancedb's async filter-only query builder: .where(...) is a
    sync builder step, .to_list() is the async terminal call — matching lancedb.AsyncQuery.
    Actually applies the `number = '...'` / `number IN (...)` filter CodeRepository builds
    (by picking quoted values back out of it), so tests exercise real filtering behavior
    rather than a query object that ignores its own filter."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.last_where: str | None = None

    def where(self, filter_str: str) -> "_FakeSearchQuery":
        self.last_where = filter_str
        wanted = {v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", filter_str)}
        self._rows = [row for row in self._rows if row["number"] in wanted]
        return self

    async def to_list(self) -> list[dict]:
        return self._rows


class _FakeTable:
    """In-memory stand-in for the real `codes` lancedb AsyncTable: .query() returns a query
    object pre-loaded with whichever rows the test wants back, and records the filter
    string CodeRepository built so tests can assert on the actual escaping/quoting logic."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.queries: list[_FakeSearchQuery] = []

    def query(self) -> _FakeSearchQuery:
        query = _FakeSearchQuery(self.rows)
        self.queries.append(query)
        return query


def _reader(table: _FakeTable) -> CodeRepository:
    return CodeRepository(table)


def _row(number: str, **fields) -> dict:
    return {
        "number": number,
        "description": "",
        "when_to_use": [],
        "rules": [],
        "fees": [],
        "confidence": 1.0,
        **fields,
    }


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        ICodeRepository()


async def test_get_by_number_returns_validated_code_row():
    table = _FakeTable([_row("15801", description="Visite de prise en charge", confidence=0.9)])
    reader = _reader(table)

    row = await reader.get_by_number("15801")

    assert isinstance(row, CodeRow)
    assert row.number == "15801"
    assert row.description == "Visite de prise en charge"
    assert row.confidence == 0.9


async def test_get_by_number_filters_by_quoted_number():
    table = _FakeTable([_row("15801")])
    reader = _reader(table)

    await reader.get_by_number("15801")

    assert table.queries[0].last_where == "number = '15801'"


async def test_get_by_number_escapes_single_quotes_in_id():
    table = _FakeTable([_row("15'801")])
    reader = _reader(table)

    await reader.get_by_number("15'801")

    assert table.queries[0].last_where == "number = '15''801'"


async def test_get_by_number_raises_when_no_row_matches():
    table = _FakeTable([])
    reader = _reader(table)

    with pytest.raises(ValueError, match="found 0"):
        await reader.get_by_number("missing")


async def test_get_by_number_raises_when_more_than_one_row_matches():
    table = _FakeTable([_row("15801"), _row("15801")])
    reader = _reader(table)

    with pytest.raises(ValueError, match="found 2"):
        await reader.get_by_number("15801")


async def test_list_by_numbers_returns_validated_code_rows_for_every_id():
    table = _FakeTable([_row("A", description="a"), _row("B", description="b")])
    reader = _reader(table)

    rows = await reader.list_by_numbers(["A", "B"])

    assert [r.number for r in rows] == ["A", "B"]
    assert all(isinstance(r, CodeRow) for r in rows)


async def test_list_by_numbers_filters_by_quoted_ids():
    table = _FakeTable([_row("A"), _row("B")])
    reader = _reader(table)

    await reader.list_by_numbers(["A", "B"])

    assert table.queries[0].last_where == "number IN ('A', 'B')"


async def test_list_by_numbers_returns_empty_list_for_empty_input():
    table = _FakeTable([_row("A")])
    reader = _reader(table)

    assert await reader.list_by_numbers([]) == []


async def test_list_by_numbers_silently_drops_ids_with_no_matching_row():
    # A retrieved candidate number with no matching `codes` row (stale embeddings index) is
    # dropped rather than raising — list_by_numbers is a best-effort bulk lookup, unlike
    # get_by_number.
    table = _FakeTable([_row("A")])
    reader = _reader(table)

    rows = await reader.list_by_numbers(["A", "MISSING"])

    assert [r.number for r in rows] == ["A"]


async def test_list_by_numbers_logs_a_warning_for_ids_with_no_matching_row(caplog):
    table = _FakeTable([_row("A")])
    reader = _reader(table)

    with caplog.at_level("WARNING", logger="app.lancedb.repository"):
        await reader.list_by_numbers(["A", "MISSING"])

    [record] = caplog.records
    assert record.levelname == "WARNING"
    assert record.missing_numbers == ["MISSING"]


async def test_list_by_numbers_logs_nothing_when_every_id_matches(caplog):
    table = _FakeTable([_row("A")])
    reader = _reader(table)

    with caplog.at_level("WARNING", logger="app.lancedb.repository"):
        await reader.list_by_numbers(["A"])

    assert caplog.records == []
