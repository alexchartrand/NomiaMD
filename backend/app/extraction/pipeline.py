"""Three-stage pipeline for billing_codes:

1. consultation_summary turns the raw transcript into structured facts.
2. The patient is already known — chosen by the physician before extraction runs, not
   guessed from the transcript — so this stage resolves the administrative facts
   billing_codes needs but can never derive from a transcript (the physician's own
   practice facts, the chosen patient's registration/vulnerability status) into a
   BillingContext.
3. billing_codes runs off the structured summary, the raw transcript, and that context.

Both the summary and the raw transcript reach stage 3 (not just the summary's rendered
text): the summary is denser and better for retrieval, but as the *only* grounding text for
selection it's a lossy bottleneck — any clinical detail the summarizer dropped is
unrecoverable downstream. See app/ramq_codes/task.py's BillingCodesInput docstring."""

import logging
from typing import cast

from app.auth.factory import get_profile_service
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.engine import run_extraction
from app.extraction.models import ExtractionResult
from app.postgresdb import PatientRepository, User
from app.ramq_codes import BillingCodesInput, BillingCodesResult, BillingContext, BillingContextBuilder, BillingCodesTask
from app.summary import ConsultationSummaryResult
from app.tasks.registry import get_task

logger = logging.getLogger(__name__)


async def _build_context(
    *, user: User, patient_id: int, encounter_date: date | None, context_builder: BillingContextBuilder
) -> BillingContext:
    # Same best-effort stance as _verify_patient above, extended to the physician-profile
    # half: a profile-lookup failure must degrade to an all-null BillingContext (billing_codes
    # falls back to today's guess-from-transcript behavior for those axes), not crash the
    # extraction the physician is waiting on.
    try:
        return await context_builder.build(user=user, patient_id=patient_id, encounter_date=encounter_date)
    except Exception:
        logger.exception("Billing context lookup failed; billing_codes proceeds with an empty context")
        return BillingContext()


async def _resolve_fees(result: BillingCodesResult) -> None:
    # Same best-effort stance as _build_context above: a LanceDB lookup failure here must
    # never discard a completed (paid-for) extraction — codes just keep their already-empty
    # fee list, identical to today's "no fee data" case.
    try:
        task = cast(BillingCodesTask, get_task("billing_codes"))
        await task.resolve_fees(result)
    except Exception:
        logger.exception("Fee resolution failed; billing_codes proceeds with no resolved fees")


async def run_billing_codes_pipeline(
    transcript: str,
    *,
    user: User,
    patient_id: int,
    context_builder: BillingContextBuilder | None = None,
    patient_repository: PatientRepository | None = None,
) -> tuple[
    ExtractionResult[ConsultationSummaryResult],
    ExtractionResult[BillingCodesResult],
]:
    """Runs all three stages and returns both extraction results — callers that only need
    the final billing codes still get the intermediate summary (e.g. to store it for
    traceability)."""
    patient_repository = patient_repository or PatientRepository()
    context_builder = context_builder or BillingContextBuilder(get_profile_service(), patient_repository)

    summary_result = await run_extraction(get_task("consultation_summary"), transcript)
    summary = summary_result.result

    encounter_date = parse_encounter_date(summary.encounter_setting.date)

    context = await _build_context(
        user=user, patient_id=patient_id, encounter_date=encounter_date, context_builder=context_builder
    )

    billing_input = BillingCodesInput(summary=summary, transcript=transcript, context=context)
    billing_result = await run_extraction(get_task("billing_codes"), billing_input)
    await _resolve_fees(billing_result.result)

    return summary_result, billing_result
