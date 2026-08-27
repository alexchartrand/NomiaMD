"""Business logic for grouping physician-confirmed claims into a generated bill.
Constructor-injected (BillRepository, ClaimRepository, PatientRepository,
UserRepository, BillPdfRenderer) — composed at the module boundary by factory.py, no
FastAPI/HTTP concerns here."""

from app.bills.models import BillDetailOut, BillOut
from app.bills.pdf import BillDocument, BillLineItem, BillPatientGroup, BillPdfRenderer
from app.claims.service import _codes_out, _detail_to_out
from app.postgresdb import (
    Bill,
    BillInput,
    BillRepository,
    ClaimRepository,
    PatientRepository,
    UserRepository,
)


class EmptySelectionError(Exception):
    pass


class StaleSelectionError(Exception):
    """A requested claim_id is missing, owned by another physician, or no longer
    "brouillon" — the candidate list the physician acted on has gone stale since it loaded."""

    pass


def _bill_number(bill_id: int) -> str:
    return f"FACT-{bill_id:06d}"


def _bill_to_out(bill: Bill) -> BillOut:
    return BillOut(
        id=bill.id,
        number=_bill_number(bill.id),
        start_date=bill.start_date,
        end_date=bill.end_date,
        generated_at=bill.generated_at,
        total_amount=bill.total_amount,
        record_count=bill.record_count,
    )


class BillService:
    def __init__(
        self,
        bill_repository: BillRepository,
        claim_repository: ClaimRepository,
        patient_repository: PatientRepository,
        user_repository: UserRepository,
        pdf_renderer: BillPdfRenderer,
    ):
        self._bill_repository = bill_repository
        self._claim_repository = claim_repository
        self._patient_repository = patient_repository
        self._user_repository = user_repository
        self._pdf_renderer = pdf_renderer

    async def create(self, *, physician_id: int, start_date, end_date, claim_ids: list[int]) -> BillOut:
        deduped = list(dict.fromkeys(claim_ids))
        if not deduped:
            raise EmptySelectionError()

        # Total is computed from each claim's own snapshotted code rows (never invented,
        # never re-derived from LanceDB) — same reasoning as ClaimCode's docstring.
        # This loop also re-validates ownership/status before the repository's own
        # transactional re-check, so a stale/foreign id is rejected with a clear error
        # instead of the generic "some ids didn't match" the repository raises.
        total = 0.0
        has_amount = False
        for claim_id in deduped:
            detail = await self._claim_repository.get_for_physician(claim_id, physician_id)
            if detail is None or detail.record.status != "brouillon":
                raise StaleSelectionError()
            claim_amount = _detail_to_out(detail).total_amount
            if claim_amount is not None:
                total += claim_amount
                has_amount = True

        bill = await self._bill_repository.create(
            BillInput(
                physician_id=physician_id,
                start_date=start_date,
                end_date=end_date,
                claim_ids=deduped,
                total_amount=total if has_amount else None,
            )
        )
        if bill is None:
            # Something changed between the validation loop above and the repository's own
            # atomic re-check (e.g. a racing second submission of an overlapping range).
            raise StaleSelectionError()
        return _bill_to_out(bill)

    async def list_for_physician(self, physician_id: int, *, limit: int = 100, offset: int = 0) -> list[BillOut]:
        bills = await self._bill_repository.list_for_physician(physician_id, limit=limit, offset=offset)
        return [_bill_to_out(b) for b in bills]

    async def get_for_physician(self, bill_id: int, physician_id: int) -> BillDetailOut | None:
        bill = await self._bill_repository.get_for_physician(bill_id, physician_id)
        if bill is None:
            return None
        claim_ids = await self._bill_repository.claim_ids_for_bill(bill_id)
        claims = []
        for claim_id in claim_ids:
            detail = await self._claim_repository.get_for_physician(claim_id, physician_id)
            if detail is not None:
                claims.append(_detail_to_out(detail))
        return BillDetailOut(**_bill_to_out(bill).model_dump(), claims=claims)

    async def render_pdf(self, bill_id: int, physician_id: int) -> bytes | None:
        bill = await self._bill_repository.get_for_physician(bill_id, physician_id)
        if bill is None:
            return None

        physician = await self._user_repository.get_by_id(physician_id)
        claim_ids = await self._bill_repository.claim_ids_for_bill(bill_id)
        details = []
        for claim_id in claim_ids:
            detail = await self._claim_repository.get_for_physician(claim_id, physician_id)
            if detail is not None:
                details.append(detail)

        patient_ids = {d.record.patient_id for d in details}
        patients = await self._patient_repository.get_many_for_physician(list(patient_ids), physician_id)
        ramq_by_patient_id = {p.id: p.ramq_number for p in patients}

        groups_by_patient: dict[int, BillPatientGroup] = {}
        for detail in sorted(details, key=lambda d: (d.patient_full_name, d.record.service_date)):
            group = groups_by_patient.setdefault(
                detail.record.patient_id,
                BillPatientGroup(
                    patient_name=detail.patient_full_name,
                    ramq_number=ramq_by_patient_id.get(detail.record.patient_id),
                    lines=[],
                ),
            )
            for code in _codes_out(detail.codes):
                group.lines.append(
                    BillLineItem(
                        service_date=detail.record.service_date,
                        code=code.code,
                        fee_amount=code.fee_amount,
                    )
                )

        document = BillDocument(
            number=_bill_number(bill.id),
            start_date=bill.start_date,
            end_date=bill.end_date,
            generated_at=bill.generated_at,
            physician_name=physician.full_name if physician is not None else "",
            physician_type=physician.physician_type if physician is not None else None,
            patient_groups=list(groups_by_patient.values()),
            total_amount=bill.total_amount,
            record_count=bill.record_count,
        )
        return self._pdf_renderer.render(document)

    async def delete(self, bill_id: int, physician_id: int) -> bool:
        return await self._bill_repository.delete_for_physician(bill_id, physician_id)
