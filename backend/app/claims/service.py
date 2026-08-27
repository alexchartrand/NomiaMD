"""Business logic for turning a physician-reviewed extraction into a claim.
Constructor-injected (ClaimRepository, PatientRepository, ExtractionRepository) —
composed at the module boundary by factory.py, no FastAPI/HTTP concerns here."""

import json
from datetime import date

from app.claims.models import ClaimCodeOut, ClaimOut
from app.postgresdb import (
    ClaimCodeInput,
    ClaimDetail,
    ClaimInput,
    ClaimRepository,
    ClaimWithCodes,
    ExtractionRepository,
    PatientRepository,
)


class PatientNotFoundError(Exception):
    pass


class ExtractionRecordNotFoundError(Exception):
    pass


class UnknownCodesError(Exception):
    def __init__(self, codes: list[str]):
        self.codes = codes
        super().__init__(f"Unknown codes: {', '.join(codes)}")


class EmptySelectionError(Exception):
    pass


class DuplicateClaimError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ClaimOnBillError(Exception):
    pass


def _total_amount(codes: list[ClaimCodeOut]) -> float | None:
    amounts = [c.fee_amount for c in codes if c.fee_amount is not None]
    return sum(amounts) if amounts else None


def _codes_out(codes) -> list[ClaimCodeOut]:
    return [ClaimCodeOut.model_validate(c) for c in codes]


def _detail_to_out(detail: ClaimDetail) -> ClaimOut:
    codes = _codes_out(detail.codes)
    return ClaimOut(
        id=detail.record.id,
        patient_id=detail.record.patient_id,
        patient_full_name=detail.patient_full_name,
        service_date=detail.record.service_date,
        status=detail.record.status,
        source_system=detail.record.source_system,
        codes=codes,
        total_amount=_total_amount(codes),
        created_at=detail.record.created_at,
        updated_at=detail.record.updated_at,
    )


class ClaimService:
    def __init__(
        self,
        claim_repository: ClaimRepository,
        patient_repository: PatientRepository,
        extraction_repository: ExtractionRepository,
    ):
        self._claim_repository = claim_repository
        self._patient_repository = patient_repository
        self._extraction_repository = extraction_repository

    async def create(
        self,
        *,
        physician_id: int,
        patient_id: int,
        service_date: date,
        billing_extraction_record_id: int,
        summary_extraction_record_id: int | None,
        selected_codes: list[str],
        source_system: str | None,
        confirm_duplicate: bool,
    ) -> ClaimOut:
        deduped_selected = list(dict.fromkeys(selected_codes))
        if not deduped_selected:
            raise EmptySelectionError()

        patient = await self._patient_repository.get_for_physician(patient_id, physician_id)
        if patient is None:
            raise PatientNotFoundError()

        extraction_record = await self._extraction_repository.get_for_user(
            billing_extraction_record_id, physician_id
        )
        if extraction_record is None or extraction_record.task != "billing_codes":
            raise ExtractionRecordNotFoundError()

        if summary_extraction_record_id is not None:
            summary_record = await self._extraction_repository.get_for_user(
                summary_extraction_record_id, physician_id
            )
            if summary_record is None:
                raise ExtractionRecordNotFoundError()

        # The billing_extraction_record_id unique constraint already enforces this at the DB
        # level; checking here first gives a clean 409 instead of a raw IntegrityError, and
        # this one is never overridable by confirm_duplicate — resubmitting the exact same
        # extraction as a second claim would be a client bug, not a legitimate re-bill.
        already_saved = await self._claim_repository.get_by_billing_extraction_record_id(
            billing_extraction_record_id
        )
        if already_saved is not None:
            raise DuplicateClaimError("Cette extraction a déjà été enregistrée comme facturation.")

        candidates_by_code: dict[str, dict] = {}
        result = json.loads(extraction_record.result_json)
        for entry in result.get("codes", []):
            candidates_by_code.setdefault(entry["code"], entry)

        unknown = [c for c in deduped_selected if c not in candidates_by_code]
        if unknown:
            raise UnknownCodesError(unknown)

        # Unlike the same-extraction case above, a physician can legitimately bill the same
        # patient twice in one day — this is a warning the caller can override, not a block.
        if not confirm_duplicate:
            existing_count = await self._claim_repository.count_for_patient_on_date(
                physician_id, patient_id, service_date
            )
            if existing_count > 0:
                raise DuplicateClaimError(
                    "Une facturation existe déjà pour ce patient à cette date."
                )

        code_inputs = [
            ClaimCodeInput(
                code=code,
                description=candidates_by_code[code]["description"],
                confidence=candidates_by_code[code]["confidence"],
                explanation=candidates_by_code[code]["explanation"],
                fee_amount=(candidates_by_code[code].get("fee") or {}).get("amount"),
                fee_when_to_use=(candidates_by_code[code].get("fee") or {}).get("when_to_use"),
                majoration=(candidates_by_code[code].get("fee") or {}).get("majoration"),
            )
            for code in deduped_selected
        ]

        created: ClaimWithCodes = await self._claim_repository.create(
            ClaimInput(
                physician_id=physician_id,
                patient_id=patient_id,
                service_date=service_date,
                status="brouillon",
                source_system=source_system,
                summary_extraction_record_id=summary_extraction_record_id,
                billing_extraction_record_id=billing_extraction_record_id,
                codes=code_inputs,
            )
        )

        codes_out = _codes_out(created.codes)
        return ClaimOut(
            id=created.record.id,
            patient_id=created.record.patient_id,
            patient_full_name=patient.full_name,
            service_date=created.record.service_date,
            status=created.record.status,
            source_system=created.record.source_system,
            codes=codes_out,
            total_amount=_total_amount(codes_out),
            created_at=created.record.created_at,
            updated_at=created.record.updated_at,
        )

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
        return [_detail_to_out(d) for d in details]

    async def delete(self, record_id: int, physician_id: int) -> bool:
        # Once a claim is on a generated bill (status != "brouillon"), it can only be freed
        # by deleting that bill — otherwise a hard delete here would leave a dangling link
        # row and silently shrink a bill's total behind the physician's back.
        detail = await self._claim_repository.get_for_physician(record_id, physician_id)
        if detail is None:
            return False
        if detail.record.status != "brouillon":
            raise ClaimOnBillError()
        return await self._claim_repository.delete_for_physician(record_id, physician_id)
