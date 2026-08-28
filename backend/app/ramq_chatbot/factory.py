from llama_index.llms.mistralai import MistralAI

from app.config import settings
from app.embedings import get_embeding_model
from app.lancedb import ICodeRepository, IDocumentRepository
from app.lancedb.converter import CodesRowConverter, DocumentRowConverter
from app.ramq_chatbot.engine import RAMQManualQueryEngine
from app.ramq_chatbot.fusion import ReciprocalRankFuser
from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_chatbot.query_generator import LLMQueryGenerator
from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.ramq_codes.codes_data import CodesData

_engine: RAMQManualQueryEngine | None = None


def init_ramq_query_engine(codes: ICodeRepository, documents: IDocumentRepository) -> None:
    """Builds the hybrid-search chatbot engine and stores it for get_ramq_query_engine() to
    return. Called once by the app lifespan (app/bootstrap.py's application_services()),
    which is also what opens `documents`/`codes` in the first place (app/lancedb/database.py)."""
    global _engine
    llm = MistralAI(
        model="mistral-small-latest",
        api_key=settings.mistral_api_key,
        temperature=0,
        max_tokens=4096,
    )
    reference_expander = ReferenceExpander(
        section_lookup=ManualSectionLookup(documents, DocumentRowConverter()),
        codes_data=CodesData(codes, CodesRowConverter()),
    )
    retriever = RAMQManualRetriever(
        documents=documents,
        embed_model=get_embeding_model(),
        query_generator=LLMQueryGenerator(llm),
        fuser=ReciprocalRankFuser(),
        converter=DocumentRowConverter(),
        reference_expander=reference_expander,
    )
    _engine = RAMQManualQueryEngine(retriever=retriever, llm=llm)


def get_ramq_query_engine() -> RAMQManualQueryEngine:
    if _engine is None:
        raise RuntimeError(
            "RAMQ chatbot engine not initialized — app/bootstrap.py's "
            "application_services() must run first"
        )
    return _engine
