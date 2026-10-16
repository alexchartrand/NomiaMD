"""The billing pipeline (consultation_summary -> context -> retrieval -> billing_codes ->
fees) and its HTTP route.

Public interface — everything else that needs this imports it from here rather than
reaching into .pipeline/.factory/.router/.models directly."""

from app.extraction.factory import build_billing_pipeline, get_billing_pipeline, init_billing_pipeline
from app.extraction.models import ExtractionRequest, TranscriptSource
from app.extraction.pipeline import BillingPipeline, PipelineResult
from app.extraction.router import router as extraction_router

__all__ = [
    "BillingPipeline",
    "PipelineResult",
    "build_billing_pipeline",
    "get_billing_pipeline",
    "init_billing_pipeline",
    "extraction_router",
    "ExtractionRequest",
    "TranscriptSource",
]
