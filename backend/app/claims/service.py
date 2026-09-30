"""Business logic for turning a physician-reviewed extraction into a claim.
Constructor-injected (ClaimRepository, PatientRepository, ExtractionRepository, plus the
ClaimDuplicateGuard and FeeSnapshotter it composes) — wired at the module boundary by
factory.py, no FastAPI/HTTP concerns here."""

from datetime import date

from app.claims.candidates import ExtractionCandidates
from app.claims.duplicates import EXTRACTION_ALREADY_CLAIMED, ClaimDuplicateGuard
from app.claims.errors import (
    ClaimOnBillError,
    DuplicateClaimError,
    EmptySelectionError,
    ExtractionRecordNotFoundError,
    PatientNotFoundError,
)
from app.claims.fees import FeeSnapshotter
from app.claims.mapper import ClaimMapper
from app.claims.models import ClaimOut, SelectedCode
from app.claims.status import ClaimLifecycle
from app.postgresdb import (
    ClaimCodeInput,
    ClaimInput,
    ClaimRepository,
    ExtractionAlreadyClaimedError,
    ExtractionRecord,
    ExtractionRepository,
    PatientRepository,
)


class ClaimService:
    def __init__(
        self,
        claim_repository: ClaimRepository,
        patient_repository: PatientRepository,
        extraction_repository: ExtractionRepository,
        duplicate_guard: ClaimDuplicateGuard,
        fee_snapshotter: FeeSnapshotter,
    ):
        self._claim_repository = claim_repository
        self._patient_repository = patient_repository
        self._extraction_repository = extraction_repository
        self._duplicate_guard = duplicate_guard
        self._fee_snapshotter = fee_snapshotter

    async def create(
        self,
        *,
        physician_id: int,
        patient_id: int,
        service_date: date,
        billing_extraction_record_id: int,
        summary_extraction_record_id: int | None,
        selected_codes: list[SelectedCode],
        source_system: str | None,
        confirm_duplicate: bool,
    ) -> ClaimOut:
        selected = self._dedupe(selected_codes)

        # Patient is a shared, global identity now — any physician may claim any known
        # patient regardless of "my patients list" membership (that list is optional
        # personal metadata, not a billing gate; see app/postgresdb/models.py's Patient).
        patient = await self._patient_repository.get(patient_id)
        if patient is None:
            raise PatientNotFoundError()

        extraction_record = await self._billing_extraction(billing_extraction_record_id, physician_id)
        if summary_extraction_record_id is not None:
            await self._owned_extraction(summary_extraction_record_id, physician_id)

        await self._duplicate_guard.ensure_extraction_unclaimed(billing_extraction_record_id)
        candidates = ExtractionCandidates.from_result_json(extraction_record.result_json).require(
            [s.code for s in selected]
        )
        if not confirm_duplicate:
            await self._duplicate_guard.ensure_first_on_date(physician_id, patient_id, service_date)

        code_inputs = []
        for choice, candidate in zip(selected, candidates):
            fee = self._fee_snapshotter.snapshot(candidate, choice.fee_index)
            code_inputs.append(
                ClaimCodeInput(
                    code=candidate.code,
                    description=candidate.description,
                    confidence=candidate.confidence,
                    explanation=candidate.explanation,
                    fee_amount=fee.amount,
                    fee_when_to_use=fee.when_to_use,
                    majoration=fee.majoration,
                )
            )

        try:
            created = await self._claim_repository.create(
                ClaimInput(
                    physician_id=physician_id,
                    patient_id=patient_id,
                    service_date=service_date,
                    status=ClaimLifecycle.INITIAL,
                    source_system=source_system,
                    summary_extraction_record_id=summary_extraction_record_id,
                    billing_extraction_record_id=billing_extraction_record_id,
                    codes=code_inputs,
                )
            )
        except ExtractionAlreadyClaimedError as exc:
            raise DuplicateClaimError(EXTRACTION_ALREADY_CLAIMED) from exc

        return ClaimMapper.to_out(created.claim, patient.full_name, created.codes)

    @staticmethod
    def _dedupe(selected_codes: list[SelectedCode]) -> list[SelectedCode]:
        """First choice per code wins; an empty selection is refused."""
        by_code: dict[str, SelectedCode] = {}
        for selected in selected_codes:
            by_code.setdefault(selected.code, selected)
        if not by_code:
            raise EmptySelectionError()
        return list(by_code.values())

    async def _owned_extraction(self, record_id: int, physician_id: int) -> ExtractionRecord:
        record = await self._extraction_repository.get_for_user(record_id, physician_id)
        if record is None:
            raise ExtractionRecordNotFoundError()
        return record

    async def _billing_extraction(self, record_id: int, physician_id: int) -> ExtractionRecord:
        record = await self._owned_extraction(record_id, physician_id)
        if record.task != "billing_codes":
            raise ExtractionRecordNotFoundError()
        return record

    async def list_for_physician(
        self,
        physician_id: int,
        *,
        patient_id: int | None,
        date_from: date | None,
        date_to: date | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[ClaimOut]:
        details = await self._claim_repository.list_for_physician(
            physician_id,
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [ClaimMapper.from_detail(d) for d in details]

    async def delete(self, claim_id: int, physician_id: int) -> bool:
        # Once a claim is on a generated bill, it can only be freed by deleting that bill —
        # otherwise a hard delete here would leave a dangling link row and silently shrink a
        # bill's total behind the physician's back.
        detail = await self._claim_repository.get_for_physician(claim_id, physician_id)
        if detail is None:
            return False
        if not ClaimLifecycle.can_be_deleted(detail.claim.status):
            raise ClaimOnBillError()
        return await self._claim_repository.delete_for_physician(claim_id, physician_id)
