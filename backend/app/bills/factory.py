"""Composition root for BillService — wires its repositories (over the request's single
session) and PDF renderer together."""

from app.bills.pdf import BillPdfRenderer
from app.bills.service import BillService
from app.postgresdb import (
    BillRepository,
    ClaimRepository,
    DbSession,
    PatientRepository,
    PhysicianProfileRepository,
    UserRepository,
)


def get_bill_service(session: DbSession) -> BillService:
    return BillService(
        BillRepository(session),
        ClaimRepository(session),
        PatientRepository(session),
        UserRepository(session),
        PhysicianProfileRepository(session),
        BillPdfRenderer(),
    )
