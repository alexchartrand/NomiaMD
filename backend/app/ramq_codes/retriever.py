
from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.llms import LLM
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.retrievers.bm25 import BM25Retriever

__all__ = ["RAMQCodesRetriever"]

class RAMQCodesRetriever(BaseRetriever):
    def __init__(
        self,
        vector_store: BasePydanticVectorStore,
        embed_model: BaseEmbedding,
        llm: LLM,
        debug: bool = False,
    ):
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
        vector_retriever = index.as_retriever(similarity_top_k=20)
        nodes = vector_store.get_nodes()
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=nodes, similarity_top_k=20)

        self.retriever = QueryFusionRetriever(
            [vector_retriever, bm25_retriever],
            llm=llm,
            similarity_top_k=20,
            num_queries=1,  # set this to 1 to disable query generation
            mode= FUSION_MODES.RELATIVE_SCORE,
            use_async=False,
            verbose=debug,)
        
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        hits = self.retriever.retrieve(query_bundle)

        return hits

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        hits = await self.retriever.aretrieve(query_bundle)
        return hits


