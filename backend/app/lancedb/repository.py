"""Read access to the LanceDB tables in models.py — one repository class per table, each
owning its own query building and row validation. Mirrors app/postgresdb/repositories/;
the connection wiring lives in database.py."""

import logging
from abc import ABC, abstractmethod
from typing import List, Tuple

from lancedb import AsyncTable
from lancedb.query import MultiMatchQuery

from app.lancedb.code_versions import ICodeTableProvider
from app.lancedb.eligibility import CodeEligibilityFilter, CodeEligibilityWhereBuilder
from app.lancedb.models import CodeRow, DocumentRow

logger = logging.getLogger(__name__)

# CodeRow's fields — every CodeRepository query selects exactly these columns. Excludes
# `vector` (never crosses the wire for a hit about to become a Code), the
# lexical_terms/expansion_terms columns, which exist for MultiMatchQuery to search over
# below, not for the app to consume, and needs_review/review_reason (not consumed yet).
_CODE_ROW_COLUMNS = [
    "number",
    "description",
    "header_path",
    "when_to_use",
    "rules",
    "fees",
    "min_age",
    "max_age",
    "min_panel_size",
    "max_panel_size",
    "requires_registered",
    "requires_vulnerable",
]

# Columns ramq-ingestion's LanceCodeIndexBuilder builds a French FTS index over (its
# FTS_COLUMNS) — mirrored here rather than imported, same "the two repos share no code"
# convention as tests/test_lancedb_document_repository.py's hand-duplicated schema.
_CODE_FTS_COLUMNS = ["number", "description", "lexical_terms", "expansion_terms"]

# DocumentRow's fields, minus `vector` — every DocumentRepository query selects exactly
# these columns so the embedding never crosses the wire for a hit about to become a TextNode.
_DOCUMENT_ROW_COLUMNS = [
    "id",
    "text",
    "title",
    "url",
    "section_number",
    "page_start",
    "page_end",
    "section_references",
    "code_references",
]


class CodeRowLookupError(LookupError):
    """A by-number lookup that didn't find exactly one row in the current codes table —
    either the number isn't in this manual revision, or (a data problem upstream in
    ramq-ingestion) it appears more than once."""


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class ICodeRepository(ABC):
    @abstractmethod
    async def get_by_number(self, number: str) -> CodeRow:
        pass

    @abstractmethod
    async def list_by_numbers(
        self, numbers: List[str], eligibility: CodeEligibilityFilter | None = None
    ) -> List[CodeRow]:
        pass

    @abstractmethod
    async def hybrid_search(
        self, text: str, vector: List[float], k: int, eligibility: CodeEligibilityFilter | None = None
    ) -> List[Tuple[CodeRow, float]]:
        pass


class ICodeCatalogRepository(ICodeRepository):
    """What a physician searching the codes by hand needs on top of ICodeRepository: no
    embedding involved (a keystroke must not cost an API call), and the revision a code was
    read from, which a claim snapshots."""

    @abstractmethod
    async def keyword_search(
        self, text: str, k: int, eligibility: CodeEligibilityFilter | None = None
    ) -> List[Tuple[CodeRow, float]]:
        pass

    @abstractmethod
    async def list_by_number_prefix(
        self, prefix: str, k: int, eligibility: CodeEligibilityFilter | None = None
    ) -> List[CodeRow]:
        pass

    @abstractmethod
    async def current_revision(self) -> str:
        pass


class CodeRepository(ICodeCatalogRepository):
    """Queries whichever `codes_<rev>` table the `code_versions` registry currently marks as
    current (code_versions.py), re-resolved on every call so a promote takes effect without
    a restart. Each revision table has one row per `number`, so no revision filter is
    needed. The async lancedb connection is established once at startup (database.py),
    never on a query."""

    def __init__(self, tables: ICodeTableProvider, where_builder: CodeEligibilityWhereBuilder | None = None):
        self._tables = tables
        self._where_builder = where_builder or CodeEligibilityWhereBuilder()

    async def get_by_number(self, number: str) -> CodeRow:
        table = await self._tables.current()
        rows = (
            await table.query()
            .where(f"number = {_quote(number)}")
            .select(_CODE_ROW_COLUMNS)
            .to_list()
        )

        if len(rows) != 1:
            raise CodeRowLookupError(f"Expected exactly one code row for number={number!r}, found {len(rows)}")

        return CodeRow.model_validate(rows[0])

    async def list_by_numbers(
        self, numbers: List[str], eligibility: CodeEligibilityFilter | None = None
    ) -> List[CodeRow]:
        """With `eligibility`, a number whose row contradicts a known fact is simply absent
        from the result, like an unknown one — callers compare against what they asked for."""
        if not numbers:
            return []
        # Quote-escape rather than trust code numbers are always digit-only, since they come
        # from a retrieved embedding hit or a request body rather than a hardcoded source.
        quoted = ", ".join(_quote(n) for n in numbers)
        table = await self._tables.current()
        rows = (
            await table.query()
            .where(self._and(f"number IN ({quoted})", eligibility))
            .select(_CODE_ROW_COLUMNS)
            .to_list()
        )
        results = [CodeRow.model_validate(row) for row in rows]

        missing = sorted(set(numbers) - {r.number for r in results})
        if missing and eligibility is None:
            logger.warning(
                "Candidate RAMQ code number(s) not found in the codes table (stale "
                "embeddings index?) — dropped from results",
                extra={"missing_numbers": missing},
            )

        return results

    async def hybrid_search(
        self, text: str, vector: List[float], k: int, eligibility: CodeEligibilityFilter | None = None
    ) -> List[Tuple[CodeRow, float]]:
        # Same nearest_to(...) + nearest_to_text(...) chain as DocumentRepository.hybrid_search
        # below, with a MultiMatchQuery in place of a bare string: nearest_to_text takes
        # `str | FullTextQuery`, and MultiMatchQuery (a FullTextQuery) is what lets one call
        # search every FTS column at once instead of just one. Like the plain-string case,
        # this does NOT raise when the FTS indices are missing — it silently falls back to an
        # unindexed scan (verified empirically), harmless as long as ramq-ingestion's
        # LanceCodeIndexBuilder actually built them, which it does at ingestion time.
        #
        # The eligibility WHERE applies to both halves of the hybrid query, so a variant that
        # contradicts a known fact never takes one of the k slots (verified against the real
        # table). Null bounds always pass — see eligibility.py.
        table = await self._tables.current()
        query = (
            table.query()
            .nearest_to(vector)
            .distance_type("cosine")
            .nearest_to_text(MultiMatchQuery(text, columns=_CODE_FTS_COLUMNS))
        )
        where = self._where_builder.build(eligibility) if eligibility is not None else None
        if where is not None:
            query = query.where(where)
        rows = await query.limit(k).select(_CODE_ROW_COLUMNS).to_list()
        return [(CodeRow.model_validate(row), row["_relevance_score"]) for row in rows]

    async def keyword_search(
        self, text: str, k: int, eligibility: CodeEligibilityFilter | None = None
    ) -> List[Tuple[CodeRow, float]]:
        # The FTS half of hybrid_search alone, over the same French-stemmed, trigram indices:
        # partial words ("sutur", "infiltr") match, and no embedding call is made. `_score`
        # is selected explicitly — LanceDB's auto-projection of it is deprecated.
        table = await self._tables.current()
        query = table.query().nearest_to_text(MultiMatchQuery(text, columns=_CODE_FTS_COLUMNS))
        where = self._where_builder.build(eligibility) if eligibility is not None else None
        if where is not None:
            query = query.where(where)
        rows = await query.limit(k).select([*_CODE_ROW_COLUMNS, "_score"]).to_list()
        return [(CodeRow.model_validate(row), row["_score"]) for row in rows]

    async def list_by_number_prefix(
        self, prefix: str, k: int, eligibility: CodeEligibilityFilter | None = None
    ) -> List[CodeRow]:
        # LIKE wildcards in `prefix` would widen the match; callers pass digits only (see
        # app/code_catalog/query.py), and the quote-escape still guards the literal itself.
        table = await self._tables.current()
        rows = (
            await table.query()
            .where(self._and(f"number LIKE {_quote(prefix + '%')}", eligibility))
            .select(_CODE_ROW_COLUMNS)
            .to_list()
        )
        # Sorted here rather than in the query: LanceDB's query builder has no ORDER BY, and
        # a prefix of a few digits matches at most a few thousand small rows.
        return sorted((CodeRow.model_validate(row) for row in rows), key=lambda r: r.number)[:k]

    async def current_revision(self) -> str:
        return (await self._tables.current_version()).manual_rev

    def _and(self, clause: str, eligibility: CodeEligibilityFilter | None) -> str:
        where = self._where_builder.build(eligibility) if eligibility is not None else None
        return clause if where is None else f"({clause}) AND {where}"


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
