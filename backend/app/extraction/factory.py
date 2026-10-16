"""The process's billing pipeline. Built and set once by app/bootstrap.py's
application_services() — not at import time, since its retriever needs an already-open
LanceDB connection — and by tests' small_reference_table fixture with stubbed collaborators."""

from app.extraction.pipeline import BillingPipeline, ContextBuilder
from app.extraction.scoped_context import ScopedBillingContextBuilder
from app.lancedb import ICodeRepository
from app.ramq_codes import CodeSelector, FeeResolver, ICodesRetriever, build_ramq_retriever
from app.summary import ConsultationSummarizer

_pipeline: BillingPipeline | None = None


def build_billing_pipeline(
    codes: ICodeRepository,
    *,
    retriever: ICodesRetriever | None = None,
    context_builder: ContextBuilder | None = None,
) -> BillingPipeline:
    """`retriever`: None = the real hybrid-search one over `codes`."""
    return BillingPipeline(
        summarizer=ConsultationSummarizer(),
        context_builder=context_builder or ScopedBillingContextBuilder(),
        retriever=retriever or build_ramq_retriever(codes),
        selector=CodeSelector(),
        fees=FeeResolver(codes),
    )


def init_billing_pipeline(pipeline: BillingPipeline) -> None:
    global _pipeline
    _pipeline = pipeline


def get_billing_pipeline() -> BillingPipeline:
    if _pipeline is None:
        raise RuntimeError(
            "Billing pipeline not initialized — app/bootstrap.py's application_services() must run first"
        )
    return _pipeline
