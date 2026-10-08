from app.lancedb import ICodeRepository
from app.lancedb.fusion import DEFAULT_K, ReciprocalRankFuser
from app.llm import IEmbeddingClient, get_embedding_client
from app.ramq_codes.converter import CodesRowConverter
from app.ramq_codes.retriever import DEFAULT_FUSED_TOP_K, DEFAULT_SIMILARITY_TOP_K, RAMQCodesRetriever


def build_ramq_retriever(
    codes: ICodeRepository,
    *,
    embedding_client: IEmbeddingClient | None = None,
    similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K,
    fused_top_k: int = DEFAULT_FUSED_TOP_K,
    rrf_k: float = DEFAULT_K,
) -> RAMQCodesRetriever:
    """The ICodesRetriever BillingCodesTask is constructed with (see app/tasks/registry.py).
    The keyword arguments are the benchmark's tuning knobs; production uses the defaults."""
    return RAMQCodesRetriever(
        codes,
        embedding_client or get_embedding_client(),
        CodesRowConverter(),
        fuser=ReciprocalRankFuser(key=lambda code: code.number, k=rrf_k),
        similarity_top_k=similarity_top_k,
        fused_top_k=fused_top_k,
    )
