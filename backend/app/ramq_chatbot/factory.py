from functools import lru_cache

from llama_index.llms.mistralai import MistralAI
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.config import settings
from app.embedings import get_embeding_model
from app.ramq_chatbot.engine import RAMQManualQueryEngine
from app.ramq_chatbot.retriever import RAMQManualRetriever

TABLE_NAME = "manuel-omnipraticiens"


@lru_cache(maxsize=1)
def get_ramq_query_engine() -> RAMQManualQueryEngine:
    """Built eagerly at import time (app/ramq_chatbot/__init__.py calls this once at module
    scope), same as app/tasks/registry's BillingCodesTask: RAMQManualRetriever's BM25 index
    reads every node out of the `manuel-omnipraticiens` LanceDB table up front and tokenizes
    them, so doing this per-request would block the event loop on the first request and any
    concurrent ones. lru_cache still guards against rebuilding on incidental repeat calls."""
    vector_store = LanceDBVectorStore(
        uri=settings.db_path, table_name=TABLE_NAME, flat_metadata=False
    )
    llm = MistralAI(
        model="mistral-small-latest",
        api_key=settings.mistral_api_key,
        temperature=0,
        max_tokens=4096,
    )
    retriever = RAMQManualRetriever(
        vector_store=vector_store, llm=llm, embed_model=get_embeding_model(), debug=settings.debug
    )
    return RAMQManualQueryEngine(retriever=retriever, llm=llm)
