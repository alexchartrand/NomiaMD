from app.lancedb import ICodeRepository
from app.lancedb.fusion import DEFAULT_K, ReciprocalRankFuser
from app.llm import IEmbeddingClient, get_embedding_client
from app.ramq_codes.candidate_fuser import DEFAULT_FUSED_TOP_K, CandidateFuser
from app.ramq_codes.converter import CodesRowConverter
from app.ramq_codes.query_runner import DEFAULT_SIMILARITY_TOP_K, CodeQueryRunner
from app.ramq_codes.retriever import RAMQCodesRetriever


def build_code_query_runner(
    codes: ICodeRepository,
    *,
    embedding_client: IEmbeddingClient | None = None,
    similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K,
) -> CodeQueryRunner:
    return CodeQueryRunner(
        codes, embedding_client or get_embedding_client(), CodesRowConverter(), similarity_top_k=similarity_top_k
    )


def build_candidate_fuser(*, fused_top_k: int = DEFAULT_FUSED_TOP_K, rrf_k: float = DEFAULT_K) -> CandidateFuser:
    return CandidateFuser(ReciprocalRankFuser(key=lambda code: code.number, k=rrf_k), fused_top_k=fused_top_k)


def build_ramq_retriever(
    codes: ICodeRepository,
    *,
    embedding_client: IEmbeddingClient | None = None,
    similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K,
    fused_top_k: int = DEFAULT_FUSED_TOP_K,
    rrf_k: float = DEFAULT_K,
) -> RAMQCodesRetriever:
    """The ICodesRetriever BillingCodesTask is constructed with (see app/tasks/registry.py).
    The keyword arguments are the benchmark's tuning knobs, which it passes to
    build_code_query_runner/build_candidate_fuser directly; production uses the defaults."""
    return RAMQCodesRetriever(
        build_code_query_runner(codes, embedding_client=embedding_client, similarity_top_k=similarity_top_k),
        build_candidate_fuser(fused_top_k=fused_top_k, rrf_k=rrf_k),
    )
