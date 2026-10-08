"""RAMQ billing-code retrieval and the billing_codes task built on top of it: rendered
consultation-summary text -> candidate RAMQ codes.

Public interface — everything else that needs this task imports it from here rather than
reaching into .models/.task directly."""

from app.ramq_codes.context import AXIS_LABELS_FR, BillingContext, PatientContext, PhysicianContext
from app.ramq_codes.context_builder import BillingContextBuilder
from app.ramq_codes.converter import CodesRowConverter
from app.ramq_codes.eligibility import EligibilityFilterFactory, UnresolvedAxisDetector
from app.ramq_codes.models import BillingCodesResult, CodeFeeOut, ExtractedCode, FeeUnit
from app.ramq_codes.task import BillingCodesInput, BillingCodesTask
from app.ramq_codes.factory import (
    build_candidate_fuser,
    build_code_query_runner,
    build_family_expander,
    build_ramq_retriever,
)

__all__ = [
    "AXIS_LABELS_FR",
    "CodesRowConverter",
    "EligibilityFilterFactory",
    "UnresolvedAxisDetector",
    "BillingCodesResult",
    "build_candidate_fuser",
    "build_code_query_runner",
    "build_family_expander",
    "build_ramq_retriever",
    "BillingCodesTask",
    "BillingCodesInput",
    "BillingContext",
    "BillingContextBuilder",
    "PatientContext",
    "PhysicianContext",
    "ExtractedCode",
    "CodeFeeOut",
    "FeeUnit",
]
