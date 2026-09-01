"""Business logic for turning a physician-reviewed extraction into a claim.
Constructor-injected (ClaimRepository, PatientRepository, ExtractionRepository) —
composed at the module boundary by factory.py, no FastAPI/HTTP concerns here."""

from datetime import date
from decimal import Decimal

from app.claims.models import ClaimCodeOut, ClaimOut, SelectedCode
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


class InvalidFeeSelectionError(Exception):
    def __init__(self, code: str, fee_index: int, available: int):
        self.code = code
        self.fee_index = fee_index
        self.available = available
        super().__init__(f"fee_index {fee_index} out of range for code {code} ({available} available)")


class EmptySelectionError(Exception):
    pass


class DuplicateClaimError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ClaimOnBillError(Exception):
    pass


def _total_amount(codes: list[ClaimCodeOut]) -> Decimal | None:
    amounts = [c.fee_amount for c in codes if c.fee_amount is not None]
    return sum(amounts) if amounts else None


def _to_decimal(amount: float | None) -> Decimal | None:
    # str(amount) first: Decimal(33.15) keeps the binary float's imprecision
    # (33.14999999999999857891...); Decimal(str(33.15)) gives the exact "33.15".
    return None if amount is None else Decimal(str(amount))


def _resolve_fee(candidate: dict, fee_index: int | None) -> dict | None:
    fees = candidate.get("fees") or []
    if not fees:
        return None
    index = fee_index if fee_index is not None else 0
    if index < 0 or index >= len(fees):
        raise InvalidFeeSelectionError(candidate["code"], index, len(fees))
    return fees[index]


def _fee_when_to_use(fee: dict | None) -> str | None:
    # lieu is folded into this free-text column rather than given its own claim_codes
    # column — no Alembic in this repo, see ClaimCode's/BillClaim's docstrings
    # (app/postgresdb/models.py) for why a new column on an existing table is avoided.
    if fee is None:
        return None
    context, lieu = fee.get("context"), fee.get("lieu")
    if context and lieu:
        return f"{context} — {lieu}"
    return context or lieu


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
        selected_codes: list[SelectedCode],
        source_system: str | None,
        confirm_duplicate: bool,
    ) -> ClaimOut:
        seen_codes: set[str] = set()
        deduped_selected: list[SelectedCode] = []
        for selected in selected_codes:
            if selected.code in seen_codes:
                continue
            seen_codes.add(selected.code)
            deduped_selected.append(selected)
        if not deduped_selected:
            raise EmptySelectionError()

        # Patient is a shared, global identity now — any physician may claim any known
        # patient regardless of "my patients list" membership (that list is optional
        # personal metadata, not a billing gate; see app/postgresdb/models.py's Patient).
        patient = await self._patient_repository.get(patient_id)
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
        result = extraction_record.result_json
        for entry in result.get("codes", []):
            candidates_by_code.setdefault(entry["code"], entry)

        unknown = [sc.code for sc in deduped_selected if sc.code not in candidates_by_code]
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

        code_inputs = []
        for selected in deduped_selected:
            candidate = candidates_by_code[selected.code]
            chosen_fee = _resolve_fee(candidate, selected.fee_index)
            code_inputs.append(
                ClaimCodeInput(
                    code=selected.code,
                    description=candidate["description"],
                    confidence=candidate["confidence"],
                    explanation=candidate["explanation"],
                    fee_amount=_to_decimal(chosen_fee.get("amount")) if chosen_fee else None,
                    fee_when_to_use=_fee_when_to_use(chosen_fee),
                    majoration=chosen_fee.get("majoration") if chosen_fee else None,
                )
            )

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
