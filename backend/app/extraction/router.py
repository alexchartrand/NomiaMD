from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import get_current_user
from app.extraction.models import ExtractionRequest, ExtractionResult
from app.extraction.pipeline import run_billing_codes_pipeline
from app.postgresdb import ExtractionRecordInput, ExtractionRepository, User
from app.ramq_codes import BillingCodesResult
from app.rate_limit import limiter
from app.tasks.registry import get_task

router = APIRouter()


@router.post("/extract", response_model=ExtractionResult[BillingCodesResult])
@limiter.limit("10/minute")
# Runs a transcript through the billing_codes pipeline (consultation_summary -> billing_codes)
# and persists both stages. POST a transcript + task="billing_codes"; returns the candidate RAMQ
# codes for physician review.
async def extract(
    request: Request,
    body: ExtractionRequest,
    current_user: User = Depends(get_current_user),
) -> ExtractionResult[BillingCodesResult]:
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

    summary_result, result = await run_billing_codes_pipeline(body.transcript)
    extraction_repository = ExtractionRepository()
    await extraction_repository.create_many(
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

    return result
