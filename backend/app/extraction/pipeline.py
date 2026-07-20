"""Two-stage pipeline for billing_codes: a raw transcript is first summarized into
structured facts (consultation_summary), then billing_codes extracts RAMQ candidates from
that summary's rendered text rather than the raw transcript directly. The summary's
denser, already-normalized text retrieves RAMQ candidates more reliably than a long
freeform dictation, and grounds the model's code/eligibility reasoning in facts already
extracted once instead of re-reading the whole transcript."""

from app.extraction.engine import run_extraction
from app.models import BillingCodesResult, ConsultationSummaryResult, ExtractionResult
from app.tasks.consultation_summary import render_for_billing_codes
from app.tasks.registry import get_task


def run_billing_codes_pipeline(
    transcript: str,
) -> tuple[ExtractionResult[ConsultationSummaryResult], ExtractionResult[BillingCodesResult]]:
    """Runs both stages and returns both results — callers that only need the final billing
    codes still get the intermediate summary, e.g. to store it for traceability."""
    summary_result = run_extraction(get_task("consultation_summary"), transcript)
    summary_text = render_for_billing_codes(summary_result.result)
    billing_result = run_extraction(get_task("billing_codes"), summary_text)
    return summary_result, billing_result
