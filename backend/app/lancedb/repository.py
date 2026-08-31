"""Read access to the LanceDB tables in models.py — one repository class per table, each
owning its own query building and row validation. Mirrors app/postgresdb/repository.py;
the connection wiring lives in database.py."""

import logging
from abc import ABC, abstractmethod
from typing import List, Tuple

from lancedb import AsyncTable
from lancedb.query import MultiMatchQuery

from app.lancedb.models import CodeRow, DocumentRow

logger = logging.getLogger(__name__)

# CodeRow's fields — every CodeRepository query selects exactly these columns. Excludes
# `vector` (never crosses the wire for a hit about to become a Code) and the
# lexical_terms/expansion_terms/needs_review/review_reason columns, which exist for
# MultiMatchQuery to search over below, not for the app to consume. `header_path` is the
# exception among the search-oriented columns: the app does consume it (see CodeRow).
_CODE_ROW_COLUMNS = ["number", "libelle", "description", "header_path", "when_to_use", "rules", "fees"]

# Columns ramq-ingestion's LanceCodeIndexBuilder builds a French FTS index over — mirrored
# here rather than imported, same "the two repos share no code" convention as
# tests/test_lancedb_document_repository.py's hand-duplicated schema.
_CODE_FTS_COLUMNS = [
    "number",
    "libelle",
    "description",
    "header_path",
    "lexical_terms",
    "expansion_terms",
]

# DocumentRow's fields, minus `vector` — every DocumentRepository query selects exactly
# these columns so the embedding never crosses the wire for a hit about to become a TextNode.
_DOCUMENT_ROW_COLUMNS = [
    "id",
    "text",
    "title",
    "section_number",
    "page_start",
    "page_end",
    "section_references",
    "code_references",
]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class ICodeRepository(ABC):
    @abstractmethod
    async def get_by_number(self, number: str) -> CodeRow:
        pass

    @abstractmethod
    async def list_by_numbers(self, numbers: List[str]) -> List[CodeRow]:
        pass

    @abstractmethod
    async def hybrid_search(self, text: str, vector: List[float], k: int) -> List[Tuple[CodeRow, float]]:
        pass


class CodeRepository(ICodeRepository):
    """Handed an already-open table by LanceDB.open() (database.py) — the async lancedb
    connection is established once at startup, never on a query."""

    def __init__(self, table: AsyncTable):
        self._table = table

    async def get_by_number(self, number: str) -> CodeRow:
        rows = (
            await self._table.query()
            .where(f"number = {_quote(number)}")
            .select(_CODE_ROW_COLUMNS)
            .to_list()
        )

        if len(rows) != 1:
            raise ValueError(f"Expected exactly one code row for number={number!r}, found {len(rows)}")

        return CodeRow.model_validate(rows[0])

    async def list_by_numbers(self, numbers: List[str]) -> List[CodeRow]:
        # Quote-escape rather than trust code numbers are always digit-only, since they come
        # from a retrieved embedding hit rather than a hardcoded source.
        quoted = ", ".join(_quote(n) for n in numbers)
        rows = (
            await self._table.query()
            .where(f"number IN ({quoted})")
            .select(_CODE_ROW_COLUMNS)
            .to_list()
        )
        results = [CodeRow.model_validate(row) for row in rows]

        missing = sorted(set(numbers) - {r.number for r in results})
        if missing:
            logger.warning(
                "Candidate RAMQ code number(s) not found in the codes table (stale "
                "embeddings index?) — dropped from results",
                extra={"missing_numbers": missing},
            )

        return results

    async def hybrid_search(self, text: str, vector: List[float], k: int) -> List[Tuple[CodeRow, float]]:
        # Same nearest_to(...) + nearest_to_text(...) chain as DocumentRepository.hybrid_search
        # below, with a MultiMatchQuery in place of a bare string: nearest_to_text takes
        # `str | FullTextQuery`, and MultiMatchQuery (a FullTextQuery) is what lets one call
        # search all five FTS columns at once instead of just one. Like the plain-string case,
        # this does NOT raise when the FTS indices are missing — it silently falls back to an
        # unindexed scan (verified empirically), harmless as long as ramq-ingestion's
        # LanceCodeIndexBuilder actually built them, which it does at ingestion time.
        rows = (
            await self._table.query()
            .nearest_to(vector)
            .distance_type("cosine")
            .nearest_to_text(MultiMatchQuery(text, columns=_CODE_FTS_COLUMNS))
            .limit(k)
            .select(_CODE_ROW_COLUMNS)
            .to_list()
        )
        return [(CodeRow.model_validate(row), row["_relevance_score"]) for row in rows]


class IDocumentRepository(ABC):
    @abstractmethod
    async def get_by_section_number(self, section_number: str) -> List[DocumentRow]:
        pass

    @abstractmethod
    async def get_by_code_reference(self, code: str) -> List[DocumentRow]:
        pass

    @abstractmethod
    async def hybrid_search(self, text: str, vector: List[float], k: int) -> List[Tuple[DocumentRow, float]]:
        pass


class DocumentRepository(IDocumentRepository):
    """Handed an already-open `documents-embeddings` table by LanceDB.open() (database.py).
    Mirrors CodeRepository's connection-ownership contract, over the flat columns
    ramq-ingestion's document_table_schema.py writes (see CLAUDE.md's `documents-embeddings`
    note) instead of LlamaIndex's nested `metadata` struct."""

    def __init__(self, table: AsyncTable):
        self._table = table

    async def get_by_section_number(self, section_number: str) -> List[DocumentRow]:
        rows = (
            await self._table.query()
            .where(f"section_number = {_quote(section_number)}")
            .select(_DOCUMENT_ROW_COLUMNS)
            .to_list()
        )
        return [DocumentRow.model_validate(row) for row in rows]

    async def get_by_code_reference(self, code: str) -> List[DocumentRow]:
        rows = (
            await self._table.query()
            .where(f"array_has(code_references, {_quote(code)})")
            .select(_DOCUMENT_ROW_COLUMNS)
            .to_list()
        )
        return [DocumentRow.model_validate(row) for row in rows]

    async def hybrid_search(self, text: str, vector: List[float], k: int) -> List[Tuple[DocumentRow, float]]:
        # nearest_to(...) + nearest_to_text(...) rather than table.search(query_type="hybrid"):
        # the latter needs a registered embedding function to vectorize `text` itself, but
        # this backend brings its own precomputed mistral-embed vector (see retriever.py) —
        # there is no registered function to call. Note this specific chain does NOT raise
        # when the `text` FTS index is missing (unlike table.search(query_type="fts")): it
        # silently falls back to an unindexed scan, same as vector search does without an ANN
        # index. Harmless as long as the index is actually built at ingestion time (it is —
        # see LanceDocumentIndexBuilder in ramq-ingestion), but a missing index degrades
        # ranking quality silently here rather than failing loudly.
        rows = (
            await self._table.query()
            .nearest_to(vector)
            .distance_type("cosine")
            .nearest_to_text(text, columns=["text"])
            .limit(k)
            .select(_DOCUMENT_ROW_COLUMNS)
            .to_list()
        )
        return [(DocumentRow.model_validate(row), row["_relevance_score"]) for row in rows]
