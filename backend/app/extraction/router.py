import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import get_current_user
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.models import (
    BillingExtractionResponse,
    ExtractedIdentitySummary,
    ExtractionRequest,
    PatientVerificationOut,
)
from app.extraction.pipeline import run_billing_codes_pipeline
from app.patients import PatientVerification
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, PatientRepository, User
from app.rate_limit import limiter
from app.tasks.registry import get_task

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_patient_verification_out(verification: PatientVerification | None) -> PatientVerificationOut | None:
    # The pipeline already ran the comparison best-effort (app/extraction/pipeline.py's
    # _verify_patient) — this is a pure data conversion from the domain shape
    # (app.patients.PatientVerification) to the API wire shape, no comparison logic here.
    if verification is None:
        return None

    return PatientVerificationOut(
        extracted=ExtractedIdentitySummary(
            name_as_stated=verification.extracted.name_as_stated,
            ramq_number_as_stated=verification.extracted.ramq_number,
            age_years=verification.extracted.age_years,
        ),
        nam_mismatch=verification.nam_mismatch,
        name_mismatch=verification.name_mismatch,
        age_mismatch=verification.age_mismatch,
    )


@router.post("/extract", response_model=BillingExtractionResponse)
@limiter.limit("10/minute")
# Runs a transcript through the billing_codes pipeline (consultation_summary -> billing_codes)
# and persists both stages. POST a transcript + task="billing_codes" + patient_id (the
# physician must choose the patient before extraction runs); returns the candidate RAMQ
# codes for physician review, plus the encounter date and an identity mismatch warning.
async def extract(
    request: Request,
    body: ExtractionRequest,
    current_user: User = Depends(get_current_user),
) -> BillingExtractionResponse:
    try:
        task = get_task(body.task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if task.name != "billing_codes":
        raise HTTPException(
            status_code=400,
            detail="Only 'billing_codes' is available via /extract",
        )

    patient = await PatientRepository().get(body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient introuvable")

    source_system = body.source.system if body.source else None

    summary_result, result, patient_verification = await run_billing_codes_pipeline(
        body.transcript, user=current_user, patient_id=body.patient_id
    )
    extraction_repository = ExtractionRepository()
    summary_record, billing_record = await extraction_repository.create_many(
        [
            ExtractionRecordInput(
                task=summary_result.task,
                transcript=body.transcript,
                result=summary_result.result.model_dump(),
                model=summary_result.model,
                source_system=source_system,
                user_id=current_user.id,
            ),
            ExtractionRecordInput(
                task=result.task,
                transcript=body.transcript,
                result=result.result.model_dump(),
                model=result.model,
                source_system=source_system,
                user_id=current_user.id,
            ),
        ]
    )

    encounter_date_raw = summary_result.result.encounter_setting.date
    encounter_date = parse_encounter_date(encounter_date_raw)

    return BillingExtractionResponse(
        billing=result,
        summary_extraction_record_id=summary_record.id,
        billing_extraction_record_id=billing_record.id,
        encounter_date=encounter_date,
        encounter_date_raw=encounter_date_raw,
        patient_verification=_to_patient_verification_out(patient_verification),
    )
