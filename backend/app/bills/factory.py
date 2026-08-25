"""Composition root for BillService — wires its repositories and PDF renderer together."""

from app.bills.pdf import BillPdfRenderer
from app.bills.service import BillService
from app.postgresdb import BillingRecordRepository, BillRepository, PatientRepository, UserRepository


def get_bill_service() -> BillService:
    return BillService(
        BillRepository(),
        BillingRecordRepository(),
        PatientRepository(),
        UserRepository(),
        BillPdfRenderer(),
    )
