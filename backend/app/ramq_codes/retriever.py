from abc import ABC, abstractmethod
from typing import List

from llama_index.core.base.embeddings.base import BaseEmbedding

from app.lancedb.converter import IConverter
from app.lancedb.repository import ICodeRepository
from app.ramq_codes.models import Code

__all__ = ["ICodesRetriever", "RAMQCodesRetriever"]


class ICodesRetriever(ABC):
    @abstractmethod
    async def aretrieve(self, query: str) -> List[Code]:
        pass


class RAMQCodesRetriever(ICodesRetriever):
    """Hybrid (vector + native FTS) search over the flat `codes` LanceDB table, via
    CodeRepository.hybrid_search — replaces the old VectorStoreIndex/BM25Retriever/
    QueryFusionRetriever stack (that in-memory BM25 corpus scan and English stemmer only
    existed because the previous `code-embeddings` table had no native FTS index; the flat
    `codes` table does — see ramq-ingestion's docs/plans/flat-lancedb-codes-table.md).

    Returns fully-hydrated Code objects directly: unlike the old code-embeddings hit (which
    carried nothing but a bare `number`), a hybrid_search hit already has the full row, so
    there's no separate hydrate-by-number step for BillingCodesTask to make."""

    def __init__(
        self,
        codes: ICodeRepository,
        embed_model: BaseEmbedding,
        converter: IConverter,
        similarity_top_k: int = 20,
    ):
        self._codes = codes
        self._embed_model = embed_model
        self._converter = converter
        self._similarity_top_k = similarity_top_k

    async def aretrieve(self, query: str) -> List[Code]:
        vector = await self._embed_model.aget_query_embedding(query)
        hits = await self._codes.hybrid_search(text=query, vector=vector, k=self._similarity_top_k)
        return [self._converter.convert(row) for row, _score in hits]
