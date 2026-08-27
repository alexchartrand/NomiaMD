"""Composition root for BillService — wires its repositories and PDF renderer together."""

from app.bills.pdf import BillPdfRenderer
from app.bills.service import BillService
from app.postgresdb import BillRepository, ClaimRepository, PatientRepository, UserRepository


def get_bill_service() -> BillService:
    return BillService(
        BillRepository(),
        ClaimRepository(),
        PatientRepository(),
        UserRepository(),
        BillPdfRenderer(),
    )
