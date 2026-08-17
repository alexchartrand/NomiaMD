"""Semantic candidate retrieval for RAMQ codes: a llama_index VectorStoreIndex vector search
over the `code-embeddings` LanceDB table at DB_PATH finds candidate code numbers, then each
number is joined against the `codes` table for the full row (description/when_to_use/rules/
fees). `code-embeddings` node metadata carries only `number` — not the full record — so this
retriever does that join itself before candidates_from_nodes can build a RamqCandidate.

All llama_index types stay behind RAMQCodesRetriever/candidates_from_nodes —
task.py (BillingCodesTask) only ever sees RamqCandidate objects, never a llama_index
Node/Index/Retriever directly.

Both LanceDB tables are produced by the sibling repo `ramq-ingestion`
(~/Software/ramq-ingestion) — this backend has no code dependency on how they were built, only
on their shapes: `code-embeddings` node metadata (number only; see that repo's
src/embedding/code_node_builder.py) and `codes`' flat columns (number, description,
when_to_use, rules, fees, confidence; see that repo's src/models.py Code/Fee and
src/embedding/code_record_builder.py). Nothing here carries a structured eligibility tag
beyond what's in `rules`/`fees`' free text.
"""

from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.vector_stores.types import BasePydanticVectorStore

__all__ = ["RAMQCodesRetriever"]

class RAMQCodesRetriever(BaseRetriever):
    def __init__(
        self,
        vector_store: BasePydanticVectorStore,
        embed_model: BaseEmbedding,
        similarity_top_k: int = 20,
    ):
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
        self._retriever = index.as_retriever(similarity_top_k=similarity_top_k)
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        hits = self._retriever.retrieve(query_bundle)

        return hits

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # Not just BaseRetriever's default sync-under-the-hood fallback: the inner
        # VectorIndexRetriever's own _aretrieve awaits a real async network call for the
        # query embedding (MistralAIEmbedding._aget_query_embedding), which is the actual
        # blocking cost here — the local LanceDB vector search itself stays synchronous
        # either way.
        hits = await self._retriever.aretrieve(query_bundle)

        return hits


