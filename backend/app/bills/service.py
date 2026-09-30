"""Business logic for grouping physician-confirmed claims into a generated bill.
Constructor-injected (BillRepository, ClaimRepository, PatientRepository,
UserRepository, BillPdfRenderer) — composed at the module boundary by factory.py, no
FastAPI/HTTP concerns here."""

from decimal import Decimal

from app.bills.models import BillDetailOut, BillOut
from app.bills.pdf import BillDocument, BillLineItem, BillPatientGroup, BillPdfRenderer
from app.claims.service import _codes_out, _detail_to_out
from app.claims.status import ClaimLifecycle
from app.postgresdb import (
    Bill,
    BillInput,
    BillRepository,
    ClaimAlreadyBilledError,
    ClaimDetail,
    ClaimRepository,
    PatientRepository,
    PhysicianProfileRepository,
    UserRepository,
)


class EmptySelectionError(Exception):
    pass


class StaleSelectionError(Exception):
    """A requested claim_id is missing, owned by another physician, or can no longer be
    billed (ClaimLifecycle) — the candidate list the physician acted on has gone stale since
    it loaded."""

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
        profile_repository: PhysicianProfileRepository,
        pdf_renderer: BillPdfRenderer,
    ):
        self._bill_repository = bill_repository
        self._claim_repository = claim_repository
        self._patient_repository = patient_repository
        self._user_repository = user_repository
        self._profile_repository = profile_repository
        self._pdf_renderer = pdf_renderer

    async def create(self, *, physician_id: int, start_date, end_date, claim_ids: list[int]) -> BillOut:
        deduped = list(dict.fromkeys(claim_ids))
        if not deduped:
            raise EmptySelectionError()

        # Total is computed from each claim's own snapshotted code rows (never invented,
        # never re-derived from LanceDB) — same reasoning as ClaimCode's docstring.
        # Ownership and status are checked in the same transaction the bill is written in;
        # a concurrent bill racing over the same claim is caught by bill_claims' unique
        # claim_id instead (ClaimAlreadyBilledError below).
        details = await self._claim_repository.list_by_ids(physician_id, deduped)
        if len(details) != len(deduped) or not all(
            ClaimLifecycle.can_be_billed(d.record.status) for d in details
        ):
            raise StaleSelectionError()

        total = Decimal("0")
        has_amount = False
        for detail in details:
            claim_amount = _detail_to_out(detail).total_amount
            if claim_amount is not None:
                total += claim_amount
                has_amount = True

        try:
            bill = await self._bill_repository.create(
                BillInput(
                    physician_id=physician_id,
                    start_date=start_date,
                    end_date=end_date,
                    claim_ids=deduped,
                    total_amount=total if has_amount else None,
                )
            )
        except ClaimAlreadyBilledError as exc:
            raise StaleSelectionError() from exc
        await self._claim_repository.set_status(deduped, ClaimLifecycle.ON_BILLED)
        return _bill_to_out(bill)

    async def list_for_physician(self, physician_id: int, *, limit: int, offset: int) -> list[BillOut]:
        bills = await self._bill_repository.list_for_physician(physician_id, limit=limit, offset=offset)
        return [_bill_to_out(b) for b in bills]

    async def get_for_physician(self, bill_id: int, physician_id: int) -> BillDetailOut | None:
        bill = await self._bill_repository.get_for_physician(bill_id, physician_id)
        if bill is None:
            return None
        details = await self._bill_claims(bill_id, physician_id)
        return BillDetailOut(**_bill_to_out(bill).model_dump(), claims=[_detail_to_out(d) for d in details])

    async def render_pdf(self, bill_id: int, physician_id: int) -> bytes | None:
        bill = await self._bill_repository.get_for_physician(bill_id, physician_id)
        if bill is None:
            return None

        physician = await self._user_repository.get_by_id(physician_id)
        # The profile as it stood at the end of the billed period, not today's — a
        # physician who changed practice type since must not have last month's invoice
        # reprinted under the new one.
        profile = await self._profile_repository.get_effective_on(physician_id, bill.end_date)
        details = await self._bill_claims(bill_id, physician_id)

        patient_ids = {d.record.patient_id for d in details}
        patients = await self._patient_repository.get_many(list(patient_ids))
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
            physician_type=profile.physician_type if profile is not None else None,
            patient_groups=list(groups_by_patient.values()),
            total_amount=bill.total_amount,
            record_count=bill.record_count,
        )
        return self._pdf_renderer.render(document)

    async def _bill_claims(self, bill_id: int, physician_id: int) -> list[ClaimDetail]:
        claim_ids = await self._bill_repository.claim_ids_for_bill(bill_id)
        return await self._claim_repository.list_by_ids(physician_id, claim_ids)

    async def delete(self, bill_id: int, physician_id: int) -> bool:
        """Deleting a bill releases its claims back to their pre-bill status, in the same
        transaction — never a bill gone with its claims still frozen."""
        bill = await self._bill_repository.get_for_physician(bill_id, physician_id)
        if bill is None:
            return False
        claim_ids = await self._bill_repository.claim_ids_for_bill(bill.id)
        await self._bill_repository.delete(bill)
        await self._claim_repository.set_status(claim_ids, ClaimLifecycle.ON_BILL_DELETED)
        return True
