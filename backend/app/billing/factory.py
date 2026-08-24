"""Composition root for BillingService — wires its three repositories together."""

from app.billing.service import BillingService
from app.postgresdb import BillingRecordRepository, ExtractionRepository, PatientRepository


def get_billing_service() -> BillingService:
    return BillingService(BillingRecordRepository(), PatientRepository(), ExtractionRepository())
