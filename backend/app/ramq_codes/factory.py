from llama_index.llms.mistralai import MistralAI
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from app.embedings import get_embeding_model
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.ramq_codes.codes_data import CodesData
from app.lancedb import ICodeRepository
from app.lancedb.converter import CodesRowConverter
from app.config import settings


def build_ramq_retriever(vector_store: LanceDBVectorStore) -> RAMQCodesRetriever:
    """The BaseRetriever BillingCodesTask is constructed with (see app/tasks/registry.py).

    QueryFusionRetriever resolves an LLM at construction time regardless of num_queries
    (only skips *using* it for query generation when num_queries=1), so an explicit llm
    must be passed here — otherwise it falls back to llama_index's global default (OpenAI),
    which isn't installed in this project."""
    llm = MistralAI(
        model="mistral-small-latest",
        api_key=settings.mistral_api_key,
        temperature=0,
        max_tokens=4096,
    )
    return RAMQCodesRetriever(vector_store, get_embeding_model(), llm, settings.debug)

def build_codes_data(codes: ICodeRepository) -> CodesData:
    return CodesData(codes, CodesRowConverter())
