"""Three-stage pipeline for billing_codes:

1. consultation_summary turns the raw transcript into structured facts.
2. The patient is identified from those facts (NAM match against the physician's roster)
   and the administrative facts billing_codes needs but can never derive from a transcript
   — the physician's own practice facts, the identified patient's registration/vulnerability
   status — are resolved into a BillingContext.
3. billing_codes runs off the structured summary, the raw transcript, and that context.

Both the summary and the raw transcript reach stage 3 (not just the summary's rendered
text): the summary is denser and better for retrieval, but as the *only* grounding text for
selection it's a lossy bottleneck — any clinical detail the summarizer dropped is
unrecoverable downstream. See app/ramq_codes/task.py's BillingCodesInput docstring."""

import logging
from datetime import date

from app.auth.factory import get_profile_service
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.engine import run_extraction
from app.extraction.models import ExtractionResult
from app.patients import ExtractedIdentity, PatientSuggestion, PatientSuggestionService
from app.postgresdb import PatientRepository, User
from app.ramq_codes import BillingCodesInput, BillingCodesResult, BillingContext, BillingContextBuilder
from app.summary import ConsultationSummaryResult
from app.tasks.registry import get_task

logger = logging.getLogger(__name__)


def _extracted_identity_from_summary(summary: ConsultationSummaryResult) -> ExtractedIdentity:
    info = summary.patient_information
    return ExtractedIdentity(
        ramq_number=info.ramq_number_as_stated,
        name_as_stated=info.name_as_stated,
        age_years=info.age_years,
        age_months=info.age_months_if_infant,
        sex=info.sex_if_stated,
    )


async def _suggest_patient(
    summary: ConsultationSummaryResult,
    *,
    physician_id: int,
    on_date: date,
    patient_suggestion_service: PatientSuggestionService,
) -> PatientSuggestion | None:
    # Best-effort, same stance app/extraction/router.py's old _build_patient_suggestion
    # took: a matcher bug must never throw away a completed (paid-for) extraction — a
    # failure here just means billing_codes proceeds with an empty patient context, same as
    # if no roster match existed at all.
    try:
        extracted = _extracted_identity_from_summary(summary)
        return await patient_suggestion_service.suggest(extracted, physician_id=physician_id, on_date=on_date)
    except Exception:
        logger.exception("Patient suggestion failed; billing_codes proceeds with no patient context")
        return None


async def _build_context(
    *, user: User, matched_patient_id: int | None, encounter_date: date | None, context_builder: BillingContextBuilder
) -> BillingContext:
    # Same best-effort stance as _suggest_patient above, extended to the physician-profile
    # half: a profile-lookup failure must degrade to an all-null BillingContext (billing_codes
    # falls back to today's guess-from-transcript behavior for those axes), not crash the
    # extraction the physician is waiting on.
    try:
        return await context_builder.build(
            user=user, matched_patient_id=matched_patient_id, encounter_date=encounter_date
        )
    except Exception:
        logger.exception("Billing context lookup failed; billing_codes proceeds with an empty context")
        return BillingContext()


async def run_billing_codes_pipeline(
    transcript: str,
    *,
    user: User,
    context_builder: BillingContextBuilder | None = None,
    patient_suggestion_service: PatientSuggestionService | None = None,
) -> tuple[
    ExtractionResult[ConsultationSummaryResult],
    ExtractionResult[BillingCodesResult],
    PatientSuggestion | None,
]:
    """Runs all three stages and returns both extraction results plus the patient
    suggestion — callers that only need the final billing codes still get the intermediate
    summary (e.g. to store it for traceability) and the suggestion (e.g. to prefill the
    review UI's patient picker)."""
    context_builder = context_builder or BillingContextBuilder(get_profile_service(), PatientRepository())
    patient_suggestion_service = patient_suggestion_service or PatientSuggestionService()

    summary_result = await run_extraction(get_task("consultation_summary"), transcript)
    summary = summary_result.result

    encounter_date = parse_encounter_date(summary.encounter_setting.date)
    on_date = encounter_date or date.today()

    patient_suggestion = await _suggest_patient(
        summary, physician_id=user.id, on_date=on_date, patient_suggestion_service=patient_suggestion_service
    )
    matched_patient_id = patient_suggestion.matched_patient_id if patient_suggestion is not None else None

    context = await _build_context(
        user=user, matched_patient_id=matched_patient_id, encounter_date=encounter_date, context_builder=context_builder
    )

    billing_input = BillingCodesInput(summary=summary, transcript=transcript, context=context)
    billing_result = await run_extraction(get_task("billing_codes"), billing_input)

    return summary_result, billing_result, patient_suggestion
