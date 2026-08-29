from app.embedings import get_embeding_model
from app.ramq_codes.retriever import RAMQCodesRetriever
from app.lancedb import ICodeRepository
from app.lancedb.converter import CodesRowConverter


def build_ramq_retriever(codes: ICodeRepository) -> RAMQCodesRetriever:
    """The ICodesRetriever BillingCodesTask is constructed with (see app/tasks/registry.py)."""
    return RAMQCodesRetriever(codes, get_embeding_model(), CodesRowConverter())
