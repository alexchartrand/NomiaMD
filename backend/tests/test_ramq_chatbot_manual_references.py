"""Unit tests for app/ramq_chatbot/manual_references.py — ManualSectionLookup is a thin,
async wrapper around IDocumentRepository.get_by_section_number + IConverter.convert, pinned
here against an in-memory fake repository (no real LanceDB table)."""

from app.lancedb.converter import DocumentRowConverter
from app.lancedb.models import DocumentRow
from app.lancedb.repository import IDocumentRepository
from app.ramq_chatbot.manual_references import ManualSectionLookup


class _FakeDocumentRepository(IDocumentRepository):
    def __init__(self, rows: list[DocumentRow]):
        self._rows = rows

    async def get_by_section_number(self, section_number: str) -> list[DocumentRow]:
        return [r for r in self._rows if r.section_number == section_number]

    async def get_by_code_reference(self, code: str) -> list[DocumentRow]:
        raise NotImplementedError

    async def hybrid_search(self, text: str, vector: list[float], k: int):
        raise NotImplementedError


def _row(row_id: str, section_number: str | None) -> DocumentRow:
    return DocumentRow(id=row_id, text=f"text {row_id}", title="Guide", section_number=section_number)


def _lookup(rows: list[DocumentRow]) -> ManualSectionLookup:
    return ManualSectionLookup(_FakeDocumentRepository(rows), DocumentRowConverter())


async def test_returns_the_node_with_a_matching_section_number():
    match = _row("A", "2.2.6")
    other = _row("B", "2.2.1")
    lookup = _lookup([match, other])

    results = await lookup.aget_by_section_number("2.2.6")

    assert [n.node_id for n in results] == ["A"]


async def test_returns_empty_list_when_no_node_matches():
    lookup = _lookup([_row("A", "2.2.1")])

    assert await lookup.aget_by_section_number("9.9") == []


async def test_returns_every_node_sharing_a_section_number():
    # OversizedNodeSplitter (ramq-ingestion) splits an oversized section into multiple rows
    # that all inherit the same section_number verbatim — section_number is not unique.
    first_half = _row("A", "2.2.6")
    second_half = _row("B", "2.2.6")
    lookup = _lookup([first_half, second_half])

    results = await lookup.aget_by_section_number("2.2.6")

    assert {n.node_id for n in results} == {"A", "B"}


async def test_a_row_with_no_section_number_is_never_matched():
    lookup = _lookup([_row("A", None)])

    assert await lookup.aget_by_section_number("2.2.6") == []
