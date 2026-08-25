from llama_index.llms.mistralai import MistralAI
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.config import settings
from app.embedings import get_embeding_model
from app.lancedb import ICodeRepository
from app.lancedb.converter import CodesRowConverter
from app.ramq_chatbot.engine import RAMQManualQueryEngine
from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.ramq_codes.codes_data import CodesData

TABLE_NAME = "documents-embeddings"

_engine: RAMQManualQueryEngine | None = None


def init_ramq_query_engine(codes: ICodeRepository) -> None:
    """Builds the BM25+vector chatbot engine and stores it for get_ramq_query_engine() to
    return. Called once by the app lifespan (app/bootstrap.py's application_services()) —
    not at import time, since building it scans the whole `documents-embeddings` table."""
    global _engine
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
        codes_data=CodesData(codes, CodesRowConverter()),
    )
    retriever = RAMQManualRetriever(
        vector_store=vector_store,
        llm=llm,
        embed_model=get_embeding_model(),
        reference_expander=reference_expander,
        debug=settings.debug,
    )
    _engine = RAMQManualQueryEngine(retriever=retriever, llm=llm)


def get_ramq_query_engine() -> RAMQManualQueryEngine:
    if _engine is None:
        raise RuntimeError(
            "RAMQ chatbot engine not initialized — app/bootstrap.py's "
            "application_services() must run first"
        )
    return _engine
