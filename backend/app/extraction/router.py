import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import get_current_user
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.models import BillingExtractionResponse, ExtractionRequest
from app.extraction.pipeline import run_billing_codes_pipeline
from app.extraction.recorder import ExtractionRecorder, get_extraction_recorder
from app.postgresdb import PatientRepository, User, session_scope
from app.rate_limit import limiter
from app.tasks.registry import get_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/extract", response_model=BillingExtractionResponse)
@limiter.limit("10/minute")
# Runs a transcript through the billing_codes pipeline (consultation_summary -> billing_codes)
# and persists both stages, on a new paste Encounter holding the transcript. POST a
# transcript + task="billing_codes" + patient_id (the physician must choose the patient
# before extraction runs); returns the candidate RAMQ codes for physician review, plus the
# encounter date.
#
# Deliberately not on the per-request DbSession (app/postgresdb/dependencies.py): the
# pipeline makes two multi-second LLM calls, and a request-scoped session would hold a pooled
# connection and an open transaction across both. Each DB step below (the patient lookup, the
# pipeline's own context lookup in app/extraction/scoped_context.py, and ExtractionRecorder)
# opens its own short session_scope instead. A pipeline failure is recorded on the encounter
# (its "échec" status) before propagating.
async def extract(
    request: Request,
    body: ExtractionRequest,
    current_user: User = Depends(get_current_user),
    recorder: ExtractionRecorder = Depends(get_extraction_recorder),
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

    encounter = await recorder.open_encounter(
        note_text=body.transcript,
        source_system=body.source.system if body.source else None,
        external_encounter_id=body.source.encounter_id if body.source else None,
        user_id=current_user.id,
        patient_id=body.patient_id,
    )
    try:
        summary_result, result = await run_billing_codes_pipeline(
            body.transcript, user=current_user, patient_id=body.patient_id
        )
    except Exception as exc:
        await recorder.record_failure(encounter_id=encounter.id, user_id=current_user.id, error=exc)
        raise

    encounter_date_raw = summary_result.result.encounter_setting.date
    encounter_date = parse_encounter_date(encounter_date_raw)

    run = await recorder.save(
        encounter_id=encounter.id,
        user_id=current_user.id,
        patient_id=body.patient_id,
        service_date=encounter_date,
        stages=[summary_result, result],
    )

    return BillingExtractionResponse(
        billing=result,
        extraction_run_id=run.id,
        encounter_date=encounter_date,
        encounter_date_raw=encounter_date_raw,
    )
