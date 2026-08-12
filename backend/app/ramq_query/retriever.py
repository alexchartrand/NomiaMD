from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever

class RAMQManualRetriever(BaseRetriever):
    QUERY_GEN_PROMPT = (
    "You are a helpful assistant that generates multiple search queries based on a "
    "single input query."
    "Queries will be used to retrieve billing information for family doctors." 
    "Informations will then be taken taken from the RAMQ billing manual. Location is Quebec, Canada."
    "Result must be in French. Use medical billing terminology if possible.\n"
    "Generate {num_queries} search queries, one on each line, "
    "related to the following input query:\n"
    "Query: {query}\n"
    "Queries:\n")

    def __init__(self, vector_store: BasePydanticVectorStore):
        index = VectorStoreIndex.from_vector_store(vector_store)
        vector_retriever = index.as_retriever(similarity_top_k=6)
        nodes = vector_store.get_nodes()
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=nodes, similarity_top_k=6)

        self.retriever = QueryFusionRetriever(
            [vector_retriever, bm25_retriever],
            similarity_top_k=6,
            num_queries=4,  # set this to 1 to disable query generation
            mode= "reciprocal_rerank",
            use_async=False,
            verbose=True,
            query_gen_prompt=self.QUERY_GEN_PROMPT)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self.retriever.retrieve(query_bundle)