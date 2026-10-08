"""Startup check that the query-embedding model and the stored LanceDB vectors live in the
same space. A model swap (EMBEDDING_PROVIDER, EMBEDDING_MODEL) without re-embedding the
tables in ramq-ingestion would otherwise run silently: vector search would return
meaningless neighbours and only the FTS half of hybrid search would still work.

Only the dimension can be compared: ramq-ingestion doesn't record which model built the
vectors (see its BACKLOG.md). Two different models with the same dimension pass."""

from collections.abc import Mapping

from app.llm.client import IEmbeddingClient
from app.llm.usage import call_purpose

# Embedded once at startup; its content is irrelevant, only the vector's length is read.
PROBE_TEXT = "dimension probe"


class EmbeddingDimensionMismatchError(RuntimeError):
    pass


class EmbeddingDimensionGuard:
    def __init__(self, embedding_client: IEmbeddingClient):
        self._embedding_client = embedding_client

    async def check(self, stored_dimensions: Mapping[str, int]) -> None:
        """`stored_dimensions` maps each LanceDB table name to its vector column dimension.
        Raises naming every mismatched table and the query model."""
        with call_purpose("embedding_dimension_probe"):
            query_dimension = len(await self._embedding_client.embed_query(PROBE_TEXT))
        mismatched = {
            table: dimension
            for table, dimension in stored_dimensions.items()
            if dimension != query_dimension
        }
        if mismatched:
            tables = ", ".join(f"{table} (dim {dimension})" for table, dimension in mismatched.items())
            raise EmbeddingDimensionMismatchError(
                f"Query embedding model {self._embedding_client.model_name!r} produces "
                f"{query_dimension}-dim vectors, but {tables} were embedded with a different "
                "dimension. Re-embed the tables in ramq-ingestion or set EMBEDDING_PROVIDER/"
                "EMBEDDING_MODEL back to the model they were built with."
            )
