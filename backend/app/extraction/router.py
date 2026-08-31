import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import get_current_user
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.models import (
    BillingExtractionResponse,
    ExtractionRequest,
    PatientSuggestionExtracted,
    PatientSuggestionOut,
)
from app.extraction.pipeline import run_billing_codes_pipeline
from app.patients import PatientSuggestion
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, User
from app.rate_limit import limiter
from app.tasks.registry import get_task

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_patient_suggestion_out(suggestion: PatientSuggestion | None) -> PatientSuggestionOut | None:
    # The pipeline already ran the matcher best-effort (app/extraction/pipeline.py's
    # _suggest_patient) — this is a pure data conversion from the domain shape
    # (app.patients.PatientSuggestion) to the API wire shape, no matcher logic left here.
    if suggestion is None:
        return None

    return PatientSuggestionOut(
        extracted=PatientSuggestionExtracted(
            name_as_stated=suggestion.extracted.name_as_stated,
            ramq_number_as_stated=suggestion.extracted.ramq_number,
            suggested_full_name=suggestion.prefill.suggested_full_name,
            suggested_ramq_number=suggestion.prefill.suggested_ramq_number,
            suggested_date_of_birth=suggestion.prefill.suggested_date_of_birth,
            date_of_birth_is_estimated=suggestion.prefill.date_of_birth_is_estimated,
            suggested_gender=suggestion.prefill.suggested_gender,
            age_years=suggestion.extracted.age_years,
        ),
        matched_patient_id=suggestion.matched_patient_id,
    )


@router.post("/extract", response_model=BillingExtractionResponse)
@limiter.limit("10/minute")
# Runs a transcript through the billing_codes pipeline (consultation_summary -> billing_codes)
# and persists both stages. POST a transcript + task="billing_codes"; returns the candidate RAMQ
# codes for physician review, plus the encounter date and a NAM-based patient suggestion.
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

    source_system = body.source.system if body.source else None

    summary_result, result, patient_suggestion = await run_billing_codes_pipeline(
        body.transcript, user=current_user
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
        patient_suggestion=_to_patient_suggestion_out(patient_suggestion),
    )
