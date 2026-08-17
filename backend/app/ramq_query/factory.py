import os
from functools import lru_cache

from llama_index.llms.mistralai import MistralAI
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.embedings import get_embeding_model
from app.ramq_query.engine import RAMQManualQueryEngine
from app.ramq_query.retriever import RAMQManualRetriever

TABLE_NAME = "manuel-omnipraticiens"


@lru_cache(maxsize=1)
def get_ramq_query_engine() -> RAMQManualQueryEngine:
    """Built lazily on first call (not at import time, unlike app/tasks/registry's eager
    BillingCodesTask): RAMQManualRetriever's BM25 index reads every node out of the
    `manuel-omnipraticiens` LanceDB table up front, so constructing it needs that table to
    actually exist and needs a real MISTRAL_API_KEY — importing app/main.py (and therefore
    test collection) must not require either."""
    vector_store = LanceDBVectorStore(
        uri=os.environ["DB_PATH"], table_name=TABLE_NAME, flat_metadata=False
    )
    llm = MistralAI(
        model="mistral-medium-latest",
        api_key=os.environ["MISTRAL_API_KEY"],
        temperature=0,
        max_tokens=4096,
    )
    retriever = RAMQManualRetriever(
        vector_store=vector_store, llm=llm, embed_model=get_embeding_model()
    )
    return RAMQManualQueryEngine(retriever=retriever, llm=llm)
