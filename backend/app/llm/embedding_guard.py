"""Startup check that the query-embedding model and the stored LanceDB vectors live in the
same space. A model swap (EMBEDDING_PROVIDER, EMBEDDING_MODEL) without re-embedding the
tables in ramq-ingestion would otherwise run silently: vector search would return
meaningless neighbours and only the FTS half of hybrid search would still work.

Both the dimension and the model are compared. The dimension alone isn't enough: Cohere
Embed v4 at 1024 dims has mistral-embed's width. ramq-ingestion records the model as
`<provider>:<model>` in each table's schema metadata; a table built before it did records
nothing, and was always embedded with mistral-embed (ramq-ingestion's own
LEGACY_EMBEDDING_MODEL)."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.llm.client import IEmbeddingClient
from app.llm.usage import call_purpose

# Embedded once at startup; its content is irrelevant, only the vector's length is read.
PROBE_TEXT = "dimension probe"

# What built a table that doesn't record its embedding model.
UNRECORDED_EMBEDDING_MODEL = "mistral:mistral-embed"


@dataclass(frozen=True)
class StoredEmbedding:
    """How one LanceDB table's vectors were built: the vector column's width and the
    `<provider>:<model>` it records (None when it records none)."""

    dimension: int
    model: str | None = None

    @property
    def resolved_model(self) -> str:
        return self.model or UNRECORDED_EMBEDDING_MODEL


class EmbeddingModelMismatchError(RuntimeError):
    pass


class EmbeddingModelGuard:
    def __init__(self, embedding_client: IEmbeddingClient):
        self._embedding_client = embedding_client

    async def check(self, stored: Mapping[str, StoredEmbedding]) -> None:
        """`stored` maps each LanceDB table name to how its vectors were built. Raises
        naming every mismatched table and the query model."""
        with call_purpose("embedding_dimension_probe"):
            query_dimension = len(await self._embedding_client.embed_query(PROBE_TEXT))
        query_model = self._embedding_client.identity
        mismatched = {
            table: embedding
            for table, embedding in stored.items()
            if embedding.dimension != query_dimension or embedding.resolved_model != query_model
        }
        if mismatched:
            tables = ", ".join(
                f"{table} ({embedding.resolved_model}, dim {embedding.dimension})"
                for table, embedding in mismatched.items()
            )
            raise EmbeddingModelMismatchError(
                f"Query embedding model {query_model!r} produces {query_dimension}-dim vectors, "
                f"but {tables} were embedded differently. Re-embed the tables in ramq-ingestion "
                "or set EMBEDDING_PROVIDER/EMBEDDING_MODEL back to the model they were built with."
            )
