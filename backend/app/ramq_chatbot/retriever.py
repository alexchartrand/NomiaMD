from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever

from app.ramq_chatbot.reference_expansion import ReferenceExpander

QUERY_GEN_PROMPT = """
    You are a helpful assistant that generates multiple search queries based on a single input query. 
    Queries will be used to retrieve billing information for doctors in Quebec, Canada.  
      
    Generate {num_queries} search queries, one on each line, 
    related to the following input query:
    Query: {query}
    
    Rules:
    - Result must be in French.
    - Use medical billing terminology, if possible.
    - Do not suggest any billing codes."""

class RAMQManualRetriever(BaseRetriever):

    def __init__(
        self,
        vector_store: BasePydanticVectorStore,
        llm: LLM,
        embed_model: BaseEmbedding,
        reference_expander: ReferenceExpander,
        debug: bool = False,
    ):
        self._reference_expander = reference_expander
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
        vector_retriever = index.as_retriever(similarity_top_k=20)
        nodes = vector_store.get_nodes()
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=nodes, similarity_top_k=20)

        self.retriever = QueryFusionRetriever(
            [vector_retriever, bm25_retriever],
            llm=llm,
            similarity_top_k=20,
            num_queries=3,  # set this to 1 to disable query generation
            mode= FUSION_MODES.RECIPROCAL_RANK,
            use_async=False,
            verbose=debug,
            query_gen_prompt=QUERY_GEN_PROMPT)
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._reference_expander.expand(self.retriever.retrieve(query_bundle))

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        nodes = await self.retriever.aretrieve(query_bundle)
        return await self._reference_expander.aexpand(nodes)