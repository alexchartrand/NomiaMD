"""Tests for app/lancedb/repository.py's CodeRepository — built against a real, local
lancedb table (embedded/no-server/no-network) rather than a fake, matching
tests/test_lancedb_document_repository.py's own carve-out reasoning: the point of these
tests is to pin the actual query behavior LanceDB's own async query builder gives back
(MultiMatchQuery fusing several FTS columns into one hybrid search) — a fake table can't
prove any of that.

The fixture schema duplicates ramq-ingestion's codes_embedding/code_table_schema.py
column-for-column by hand rather than importing it — the two repos share no code, so this
duplication *is* the deploy contract this suite pins down (see CLAUDE.md's `codes` note): if
ramq-ingestion's writer and this backend's reader ever disagree on the table's shape, this
fixture (not a shared import) is what would need updating to notice.

No FTS index is built in these fixtures (confirmed empirically that MultiMatchQuery via
nearest_to_text silently falls back to an unindexed scan when no index exists, same as the
plain-string case DocumentRepository.hybrid_search already relies on) — building/proving the
indices themselves is ramq-ingestion's own test suite's job (test_code_index_builder.py)."""

import tempfile

import lancedb
import pyarrow as pa
import pytest

from app.lancedb.models import CodeRow
from app.lancedb.repository import CodeRepository, ICodeRepository

TABLE_NAME = "codes"
EMBED_DIM = 4

_FEE_TYPE = pa.struct(
    [
        pa.field("amount", pa.float64()),
        pa.field("amount_text", pa.string()),
        pa.field("context", pa.string()),
        pa.field("lieu", pa.string()),
        pa.field("majoration", pa.string()),
    ]
)


def _schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("number", pa.string(), nullable=False),
            pa.field("libelle", pa.string(), nullable=False),
            pa.field("description", pa.string(), nullable=False),
            pa.field("header_path", pa.string(), nullable=False),
            pa.field("when_to_use", pa.list_(pa.string()), nullable=False),
            pa.field("rules", pa.list_(pa.string()), nullable=False),
            pa.field("fees", pa.list_(_FEE_TYPE), nullable=False),
            pa.field("lexical_terms", pa.list_(pa.string()), nullable=False),
            pa.field("expansion_terms", pa.list_(pa.string()), nullable=False),
            pa.field("needs_review", pa.bool_(), nullable=False),
            pa.field("review_reason", pa.string(), nullable=True),
            pa.field("vector", pa.list_(pa.float32(), EMBED_DIM), nullable=False),
        ]
    )


def _record(
    number: str,
    libelle: str = "libelle",
    description: str = "description",
    vector: list[float] | None = None,
    lexical_terms: list[str] | None = None,
    expansion_terms: list[str] | None = None,
) -> dict:
    return {
        "number": number,
        "libelle": libelle,
        "description": description,
        "header_path": "/1/1.1",
        "when_to_use": [],
        "rules": [],
        "fees": [],
        "lexical_terms": lexical_terms or [],
        "expansion_terms": expansion_terms or [],
        "needs_review": False,
        "review_reason": None,
        "vector": vector or [0.1, 0.2, 0.3, 0.4],
    }


def _seeded_table(persist_dir: str, records: list[dict]):
    db = lancedb.connect(persist_dir)
    table = db.create_table(TABLE_NAME, schema=_schema())
    table.add(records)
    return table


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        ICodeRepository()


async def _async_repository(persist_dir: str, records: list[dict]) -> CodeRepository:
    _seeded_table(persist_dir, records)
    connection = await lancedb.connect_async(persist_dir)
    table = await connection.open_table(TABLE_NAME)
    return CodeRepository(table)


async def test_get_by_number_returns_the_matching_row():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A"), _record("B")]
        repository = await _async_repository(persist_dir, records)

        row = await repository.get_by_number("A")

        assert isinstance(row, CodeRow)
        assert row.number == "A"


async def test_list_by_numbers_returns_every_matching_row():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A"), _record("B"), _record("C")]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.list_by_numbers(["A", "C"])

        assert {r.number for r in rows} == {"A", "C"}


async def test_hybrid_search_returns_rows_with_a_relevance_score():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", description="urgence de nuit", vector=[1.0, 0.0, 0.0, 0.0]),
            _record("B", description="consultation de routine", vector=[0.0, 1.0, 0.0, 0.0]),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="urgence", vector=[1.0, 0.0, 0.0, 0.0], k=5)

        assert len(hits) >= 1
        row, score = hits[0]
        assert isinstance(row, CodeRow)
        assert row.number == "A"
        assert isinstance(score, float)


async def test_hybrid_search_limits_to_k():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record(str(i), vector=[1.0, float(i), 0.0, 0.0]) for i in range(5)]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="description", vector=[1.0, 0.0, 0.0, 0.0], k=2)

        assert len(hits) == 2


async def test_hybrid_search_never_returns_the_vector_column():
    # CodeRow has no `vector` field — .select() must omit it so it never crosses the wire
    # for a hit about to be converted to a Code and discarded (see models.py).
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A")]
        repository = await _async_repository(persist_dir, records)

        [(row, _score)] = await repository.hybrid_search(text="description", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert not hasattr(row, "vector")


async def test_hybrid_search_matches_on_lexical_terms_alone():
    # The whole point of MultiMatchQuery over five columns: a synonym that only lives in
    # lexical_terms (never in libelle/description) still surfaces its row.
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", description="quelque chose d'autre", lexical_terms=["hypertension arterielle"]),
            _record("B", description="autre chose encore"),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="hypertension", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert "A" in [row.number for row, _score in hits]


async def test_hybrid_search_matches_on_bare_code_number():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("15188"), _record("99999")]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="15188", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert "15188" in [row.number for row, _score in hits]
