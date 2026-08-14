"""Tests for app/lancedb/db.py — ITableReader's ABC contract, and CodeTable's query building
and row validation against a fake lancedb table (no real Lance dataset ever opened)."""

import re

import pytest

from app.lancedb.db import CodeTable, ITableReader
from app.lancedb.models import CodeRow


class _FakeSearchQuery:
    """Chainable stand-in for lancedb's filter-only query builder: .where(...).to_list().
    Actually applies the `number = '...'` / `number IN (...)` filter CodeTable builds (by
    picking quoted values back out of it), so tests exercise real filtering behavior rather
    than a query object that ignores its own filter."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.last_where: str | None = None

    def where(self, filter_str: str) -> "_FakeSearchQuery":
        self.last_where = filter_str
        wanted = {v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", filter_str)}
        self._rows = [row for row in self._rows if row["number"] in wanted]
        return self

    def to_list(self) -> list[dict]:
        return self._rows


class _FakeTable:
    """In-memory stand-in for the real `codes` lancedb Table: .search() returns a query
    object pre-loaded with whichever rows the test wants back, and records the filter
    string CodeTable built so tests can assert on the actual escaping/quoting logic."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.queries: list[_FakeSearchQuery] = []

    def search(self) -> _FakeSearchQuery:
        query = _FakeSearchQuery(self.rows)
        self.queries.append(query)
        return query


class _FakeDB:
    def __init__(self, table: _FakeTable):
        self._table = table

    def open_table(self, name: str) -> _FakeTable:
        assert name == "codes"
        return self._table


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
        ITableReader()


def test_code_table_opens_codes_table_at_construction():
    table = _FakeTable([])
    db = _FakeDB(table)

    reader = CodeTable(db)

    assert reader._table is table


def test_get_returns_validated_code_row():
    table = _FakeTable([_row("15801", description="Visite de prise en charge", confidence=0.9)])
    reader = CodeTable(_FakeDB(table))

    row = reader.get("15801")

    assert isinstance(row, CodeRow)
    assert row.number == "15801"
    assert row.description == "Visite de prise en charge"
    assert row.confidence == 0.9


def test_get_filters_by_quoted_number():
    table = _FakeTable([_row("15801")])
    reader = CodeTable(_FakeDB(table))

    reader.get("15801")

    assert table.queries[0].last_where == "number = '15801'"


def test_get_escapes_single_quotes_in_id():
    table = _FakeTable([_row("15'801")])
    reader = CodeTable(_FakeDB(table))

    reader.get("15'801")

    assert table.queries[0].last_where == "number = '15''801'"


def test_get_raises_when_no_row_matches():
    table = _FakeTable([])
    reader = CodeTable(_FakeDB(table))

    with pytest.raises(ValueError, match="found 0"):
        reader.get("missing")


def test_get_raises_when_more_than_one_row_matches():
    table = _FakeTable([_row("15801"), _row("15801")])
    reader = CodeTable(_FakeDB(table))

    with pytest.raises(ValueError, match="found 2"):
        reader.get("15801")


def test_get_all_returns_validated_code_rows_for_every_id():
    table = _FakeTable([_row("A", description="a"), _row("B", description="b")])
    reader = CodeTable(_FakeDB(table))

    rows = reader.get_all(["A", "B"])

    assert [r.number for r in rows] == ["A", "B"]
    assert all(isinstance(r, CodeRow) for r in rows)


def test_get_all_filters_by_quoted_ids():
    table = _FakeTable([_row("A"), _row("B")])
    reader = CodeTable(_FakeDB(table))

    reader.get_all(["A", "B"])

    assert table.queries[0].last_where == "number IN ('A', 'B')"


def test_get_all_returns_empty_list_for_empty_input():
    table = _FakeTable([_row("A")])
    reader = CodeTable(_FakeDB(table))

    assert reader.get_all([]) == []


def test_get_all_silently_drops_ids_with_no_matching_row():
    # A retrieved candidate number with no matching `codes` row (stale embeddings index) is
    # dropped rather than raising — get_all is a best-effort bulk lookup, unlike get().
    table = _FakeTable([_row("A")])
    reader = CodeTable(_FakeDB(table))

    rows = reader.get_all(["A", "MISSING"])

    assert [r.number for r in rows] == ["A"]
