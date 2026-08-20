from functools import lru_cache

from llama_index.llms.mistralai import MistralAI
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.config import settings
from app.embedings import get_embeding_model
from app.lancedb import get_codes_table_reader
from app.lancedb.converter import CodesRowConverter
from app.ramq_chatbot.engine import RAMQManualQueryEngine
from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.ramq_codes.codes_data import CodesData

TABLE_NAME = "documents-embeddings"


@lru_cache(maxsize=1)
def get_ramq_query_engine() -> RAMQManualQueryEngine:
    vector_store = LanceDBVectorStore(
        uri=settings.ramq_chatbot_db_path, table_name=TABLE_NAME, flat_metadata=False
    )
    llm = MistralAI(
        model="mistral-small-latest",
        api_key=settings.mistral_api_key,
        temperature=0,
        max_tokens=4096,
    )
    reference_expander = ReferenceExpander(
        section_lookup=ManualSectionLookup(vector_store),
        codes_data=CodesData(get_codes_table_reader(), CodesRowConverter()),
    )
    retriever = RAMQManualRetriever(
        vector_store=vector_store,
        llm=llm,
        embed_model=get_embeding_model(),
        reference_expander=reference_expander,
        debug=settings.debug,
    )
    return RAMQManualQueryEngine(retriever=retriever, llm=llm)
