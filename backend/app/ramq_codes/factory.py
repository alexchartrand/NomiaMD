from app.embedings import get_embeding_model
from functools import lru_cache
from llama_index.llms.mistralai import MistralAI
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.ramq_codes.codes_data import CodesData
from app.lancedb import get_codes_table_reader, get_vectorstore
from app.lancedb.converter import CodesRowConverter
from app.config import settings

@lru_cache(maxsize=1)
def get_ramq_retriever() -> RAMQCodesRetriever:
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
    return RAMQCodesRetriever(get_vectorstore(), get_embeding_model(), llm, settings.debug)

def get_codes_data() -> CodesData:
    return CodesData(get_codes_table_reader(), CodesRowConverter())