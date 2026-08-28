"""Tests for app/lancedb/repository.py's DocumentRepository — built against a real, local
lancedb table (embedded/no-server/no-network) rather than a fake, matching
tests/test_lancedb_repository.py's own carve-out reasoning for CodeRepository: the point of
these tests is to pin the actual query behavior LanceDB's own async query builder gives back
(array_has/LabelList filtering, hybrid nearest_to+nearest_to_text fusion, NULL-preserving
scalar columns) — a fake table can't prove any of that.

The fixture schema duplicates ramq-ingestion's document_table_schema.py column-for-column
by hand rather than importing it — the two repos share no code, so this duplication *is* the
deploy contract this suite pins down (see CLAUDE.md's `documents-embeddings` note): if
ramq-ingestion's writer and this backend's reader ever disagree on the table's shape, this
fixture (not a shared import) is what would need updating to notice."""

import tempfile

import lancedb
import pyarrow as pa
import pytest

from app.lancedb.models import DocumentRow
from app.lancedb.repository import DocumentRepository, IDocumentRepository

TABLE_NAME = "documents-embeddings"
EMBED_DIM = 4


def _schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string(), nullable=False),
            pa.field("doc_id", pa.string(), nullable=False),
            pa.field("text", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), EMBED_DIM), nullable=False),
            pa.field("file_name", pa.string(), nullable=False),
            pa.field("title", pa.string(), nullable=False),
            pa.field("description", pa.string(), nullable=False),
            pa.field("url", pa.string(), nullable=False),
            pa.field("latest_rev", pa.string(), nullable=False),
            pa.field("chunk_count", pa.int32(), nullable=False),
            pa.field("header_path", pa.string(), nullable=False),
            pa.field("section_number", pa.string(), nullable=True),
            pa.field("page_start", pa.int32(), nullable=True),
            pa.field("page_end", pa.int32(), nullable=True),
            pa.field("section_references", pa.list_(pa.string()), nullable=True),
            pa.field("code_references", pa.list_(pa.string()), nullable=True),
        ]
    )


def _record(
    row_id: str,
    text: str = "texte",
    vector: list[float] | None = None,
    section_number: str | None = None,
    code_references: list[str] | None = None,
) -> dict:
    return {
        "id": row_id,
        "doc_id": "doc-1",
        "text": text,
        "vector": vector or [0.1, 0.2, 0.3, 0.4],
        "file_name": "guide.md",
        "title": "Guide de facturation",
        "description": "desc",
        "url": "https://example.test",
        "latest_rev": "1",
        "chunk_count": 1,
        "header_path": "/1/1.1",
        "section_number": section_number,
        "page_start": None,
        "page_end": None,
        "section_references": None,
        "code_references": code_references,
    }


def _seeded_table(persist_dir: str, records: list[dict]):
    db = lancedb.connect(persist_dir)
    table = db.create_table(TABLE_NAME, schema=_schema())
    table.add(records)
    return table


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        IDocumentRepository()


async def _async_repository(persist_dir: str, records: list[dict]) -> DocumentRepository:
    _seeded_table(persist_dir, records)
    connection = await lancedb.connect_async(persist_dir)
    table = await connection.open_table(TABLE_NAME)
    return DocumentRepository(table)


async def test_get_by_section_number_returns_only_matching_rows_and_ignores_nulls():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", section_number="2.2.6"),
            _record("B", section_number="2.2.1"),
            _record("C", section_number=None),  # absent ⇒ NULL, never matches
        ]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.get_by_section_number("2.2.6")

        assert [r.id for r in rows] == ["A"]
        assert all(isinstance(r, DocumentRow) for r in rows)


async def test_get_by_section_number_escapes_single_quotes():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A", section_number="2.2'6")]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.get_by_section_number("2.2'6")

        assert [r.id for r in rows] == ["A"]


async def test_get_by_section_number_returns_every_row_sharing_a_section_number():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", section_number="2.2.6"),
            _record("B", section_number="2.2.6"),
        ]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.get_by_section_number("2.2.6")

        assert {r.id for r in rows} == {"A", "B"}


async def test_get_by_code_reference_uses_array_has_against_a_real_labellist_index():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", code_references=["10222", "00837"]),
            _record("B", code_references=["00103"]),
            _record("C", code_references=None),
        ]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.get_by_code_reference("00837")

        assert [r.id for r in rows] == ["A"]


async def test_get_by_code_reference_escapes_single_quotes():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A", code_references=["10'22"])]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.get_by_code_reference("10'22")

        assert [r.id for r in rows] == ["A"]


async def test_hybrid_search_returns_rows_with_a_relevance_score():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", text="urgence de nuit", vector=[1.0, 0.0, 0.0, 0.0]),
            _record("B", text="consultation de routine", vector=[0.0, 1.0, 0.0, 0.0]),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="urgence", vector=[1.0, 0.0, 0.0, 0.0], k=5)

        assert len(hits) >= 1
        row, score = hits[0]
        assert isinstance(row, DocumentRow)
        assert row.id == "A"
        assert isinstance(score, float)


async def test_hybrid_search_limits_to_k():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record(str(i), vector=[1.0, float(i), 0.0, 0.0]) for i in range(5)]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="texte", vector=[1.0, 0.0, 0.0, 0.0], k=2)

        assert len(hits) == 2


async def test_hybrid_search_never_returns_the_vector_column():
    # DocumentRow has no `vector` field — .select() must omit it so it never crosses the
    # wire for a hit about to be converted to a TextNode and discarded (see models.py).
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A")]
        repository = await _async_repository(persist_dir, records)

        [(row, _score)] = await repository.hybrid_search(text="texte", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert not hasattr(row, "vector")
