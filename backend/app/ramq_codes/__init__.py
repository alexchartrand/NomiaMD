"""RAMQ billing-code retrieval and the billing_codes task built on top of it: rendered
consultation-summary text -> candidate RAMQ codes.

Public interface — everything else that needs this task imports it from here rather than
reaching into .models/.task directly."""

from app.ramq_codes.models import BillingCodesResult, ExtractedCode, ExtractedFee
from app.ramq_codes.task import BillingCodesTask
from app.ramq_codes.factory import get_ramq_retriever, get_codes_data

__all__ = ["BillingCodesResult", "get_ramq_retriever", "get_codes_data", "BillingCodesTask", "ExtractedCode", "ExtractedFee"]
