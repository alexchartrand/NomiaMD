"""RAMQ billing-code retrieval and the billing_codes step built on top of it: consultation
summary -> candidate RAMQ codes -> the model's selection -> fees.

Public interface — everything else that needs it imports it from here rather than reaching
into the modules directly."""

from app.ramq_codes.context import AXIS_LABELS_FR, BillingContext, PatientContext, PhysicianContext, ShiftContext
from app.ramq_codes.context_builder import BillingContextBuilder
from app.ramq_codes.converter import CodesRowConverter
from app.ramq_codes.eligibility import EligibilityFilterFactory, UnresolvedAxisDetector
from app.ramq_codes.models import BillingCodesResult, CodeFeeOut, ExtractedCode, FeeUnit
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.fees import FeeResolver
from app.ramq_codes.prompt import BillingPrompt, BillingPromptBuilder
from app.ramq_codes.retriever import ICodesRetriever
from app.ramq_codes.selection_parser import ParsedSelection, SelectionDrops, SelectionParser
from app.ramq_codes.selector import CodeSelection, CodeSelector
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
    "BillingPrompt",
    "BillingPromptBuilder",
    "CandidateSet",
    "CodeSelection",
    "CodeSelector",
    "FeeResolver",
    "ICodesRetriever",
    "ParsedSelection",
    "SelectionDrops",
    "SelectionParser",
    "BillingContext",
    "BillingContextBuilder",
    "PatientContext",
    "PhysicianContext",
    "ShiftContext",
    "ExtractedCode",
    "CodeFeeOut",
    "FeeUnit",
]
