"""Startup check that the query-embedding model and the stored LanceDB vectors live in the
same space. A model swap (EMBEDDING_PROVIDER, EMBEDDING_MODEL) without re-embedding the
tables in ramq-ingestion would otherwise run silently: vector search would return
meaningless neighbours and only the FTS half of hybrid search would still work.

The model is what's compared: the dimension alone isn't enough, since Cohere Embed v4 at
1024 dims has mistral-embed's width. ramq-ingestion records the model as `<provider>:<model>`
in each table's schema metadata; a table built before it did records nothing, and was always
embedded with mistral-embed (ramq-ingestion's own LEGACY_EMBEDDING_MODEL). The width is
compared too when the client declares one (Cohere v4's is a request parameter, so the same
model can be embedded at another width). No model is called: both sides are known up front."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.llm.client import IEmbeddingClient

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

    def check(self, stored: Mapping[str, StoredEmbedding]) -> None:
        """`stored` maps each LanceDB table name to how its vectors were built. Raises
        naming every mismatched table and the query model."""
        query_model = self._embedding_client.identity
        query_dimension = self._embedding_client.dimension
        mismatched = {
            table: embedding
            for table, embedding in stored.items()
            if embedding.resolved_model != query_model
            or (query_dimension is not None and embedding.dimension != query_dimension)
        }
        if mismatched:
            tables = ", ".join(
                f"{table} ({embedding.resolved_model}, dim {embedding.dimension})"
                for table, embedding in mismatched.items()
            )
            width = f" ({query_dimension}-dim)" if query_dimension is not None else ""
            raise EmbeddingModelMismatchError(
                f"Query embedding model {query_model!r}{width} doesn't match how {tables} were "
                "embedded. Re-embed the tables in ramq-ingestion or set "
                "EMBEDDING_PROVIDER/EMBEDDING_MODEL back to the model they were built with."
            )
