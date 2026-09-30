import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import get_current_user
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.models import BillingExtractionResponse, ExtractionRequest
from app.extraction.pipeline import run_billing_codes_pipeline
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, PatientRepository, User, session_scope
from app.rate_limit import limiter
from app.tasks.registry import get_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/extract", response_model=BillingExtractionResponse)
@limiter.limit("10/minute")
# Runs a transcript through the billing_codes pipeline (consultation_summary -> billing_codes)
# and persists both stages. POST a transcript + task="billing_codes" + patient_id (the
# physician must choose the patient before extraction runs); returns the candidate RAMQ
# codes for physician review, plus the encounter date.
#
# Deliberately not on the per-request DbSession (app/postgresdb/dependencies.py): the
# pipeline makes two multi-second LLM calls, and a request-scoped session would hold a pooled
# connection and an open transaction across both. Each DB step below (and the pipeline's own
# context lookup, app/extraction/scoped_context.py) opens its own short session_scope instead.
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

    async with session_scope() as session:
        patient = await PatientRepository(session).get(body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient introuvable")

    source_system = body.source.system if body.source else None

    summary_result, result = await run_billing_codes_pipeline(
        body.transcript, user=current_user, patient_id=body.patient_id
    )
    async with session_scope() as session:
        summary_record, billing_record = await ExtractionRepository(session).create_many(
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
    )
