from app.embedings import get_embeding_model
from functools import lru_cache
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.ramq_codes.codes_data import CodesData
from app.lancedb import get_codes_table_reader, get_vectorstore
from app.lancedb.converter import CodesRowConverter

@lru_cache(maxsize=1)
def get_ramq_retriever() -> RAMQCodesRetriever:
    """The BaseRetriever BillingCodesTask is constructed with (see app/tasks/registry.py)."""
    return RAMQCodesRetriever(get_vectorstore(), get_embeding_model())

def get_codes_data() -> CodesData:
    return CodesData(get_codes_table_reader(), CodesRowConverter())