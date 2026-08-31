"""RAMQ billing-code retrieval and the billing_codes task built on top of it: rendered
consultation-summary text -> candidate RAMQ codes.

Public interface — everything else that needs this task imports it from here rather than
reaching into .models/.task directly."""

from app.ramq_codes.context import BillingContext, PatientContext, PhysicianContext
from app.ramq_codes.context_builder import BillingContextBuilder
from app.ramq_codes.models import BillingCodesResult, ExtractedCode, ExtractedFee
from app.ramq_codes.task import BillingCodesInput, BillingCodesTask
from app.ramq_codes.factory import build_ramq_retriever

__all__ = [
    "BillingCodesResult",
    "build_ramq_retriever",
    "BillingCodesTask",
    "BillingCodesInput",
    "BillingContext",
    "BillingContextBuilder",
    "PatientContext",
    "PhysicianContext",
    "ExtractedCode",
    "ExtractedFee",
]
