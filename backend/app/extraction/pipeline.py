"""The billing pipeline, one step after the other:

1. ConsultationSummarizer turns the raw transcript into structured facts.
2. The patient is already known — chosen by the physician before extraction runs, not
   guessed from the transcript — so this step resolves the administrative facts billing
   needs but can never derive from a transcript (the physician's own practice facts, the
   chosen patient's registration/vulnerability status) into a BillingContext.
3. The retriever turns the summary and that context into an eligible candidate set.
4. CodeSelector has the model pick from those candidates, given the summary, the raw
   transcript and the context.
5. FeeResolver attaches each selected code's real fees.

Both the summary and the raw transcript reach step 4: the summary is denser and better for
retrieval, but as the *only* grounding text for selection it's a lossy bottleneck — any
clinical detail the summarizer dropped would be unrecoverable downstream."""

import logging
from dataclasses import dataclass
from datetime import date, time
from typing import Protocol

from app.care_setting import CareSetting
from app.extraction.encounter_date import DateOrder, parse_encounter_date
from app.postgresdb import User
from app.ramq_codes import (
    BillingCodesResult,
    BillingContext,
    CodeSelector,
    FeeResolver,
    ICodesRetriever,
    ShiftContext,
)
from app.summary import ConsultationSummarizer, ConsultationSummaryResult

logger = logging.getLogger(__name__)


class ContextBuilder(Protocol):
    """What step 2 needs: BillingContextBuilder's `build` signature. The default,
    ScopedBillingContextBuilder, wraps it in its own short DB transaction."""

    async def build(
        self,
        *,
        user: User,
        patient_id: int,
        encounter_date: date | None,
        care_setting: CareSetting | None = None,
        shift: ShiftContext | None = None,
        encounter_time: time | None = None,
    ) -> BillingContext: ...


@dataclass(frozen=True)
class PipelineResult:
    summary: ConsultationSummaryResult
    summary_model: str
    billing: BillingCodesResult
    billing_model: str


class BillingPipeline:
    def __init__(
        self,
        summarizer: ConsultationSummarizer,
        context_builder: ContextBuilder,
        retriever: ICodesRetriever,
        selector: CodeSelector,
        fees: FeeResolver,
    ):
        self._summarizer = summarizer
        self._context_builder = context_builder
        self._retriever = retriever
        self._selector = selector
        self._fees = fees

    async def run(
        self,
        transcript: str,
        *,
        user: User,
        patient_id: int,
        date_order: DateOrder = DateOrder.DMY,
        care_setting: CareSetting | None = None,
        shift: ShiftContext | None = None,
        encounter_time: time | None = None,
    ) -> PipelineResult:
        """`date_order` is how the note's source writes slash dates; `care_setting` is where
        the encounter took place, `shift` the shift it took place in and `encounter_time` when
        it started, as its source or the physician stated them (None = unknown)."""
        summarized = await self._summarizer.summarize(transcript)
        summary = summarized.summary

        context = await self._build_context(
            user=user,
            patient_id=patient_id,
            encounter_date=parse_encounter_date(summary.encounter_setting.date, date_order),
            care_setting=care_setting,
            shift=shift,
            encounter_time=encounter_time,
        )
        candidates = await self._retriever.aretrieve(summary, context)
        selection = await self._selector.select(candidates, summary, transcript, context)
        await self._attach_fees(selection.result)

        return PipelineResult(
            summary=summary,
            summary_model=summarized.model,
            billing=selection.result,
            billing_model=selection.model,
        )

    async def _build_context(
        self,
        *,
        user: User,
        patient_id: int,
        encounter_date: date | None,
        care_setting: CareSetting | None,
        shift: ShiftContext | None,
        encounter_time: time | None,
    ) -> BillingContext:
        # Best effort: a profile-lookup failure must degrade to an all-null BillingContext
        # (every axis then stays unresolved), not crash the extraction the physician is
        # waiting on.
        try:
            return await self._context_builder.build(
                user=user,
                patient_id=patient_id,
                encounter_date=encounter_date,
                care_setting=care_setting,
                shift=shift,
                encounter_time=encounter_time,
            )
        except Exception:
            logger.exception("Billing context lookup failed; billing_codes proceeds with an empty context")
            return BillingContext()

    async def _attach_fees(self, result: BillingCodesResult) -> None:
        # Same best-effort stance as _build_context: a LanceDB lookup failure here must never
        # discard a completed (paid-for) extraction — codes just keep their empty fee list,
        # identical to the "no fee data" case.
        try:
            await self._fees.attach(result)
        except Exception:
            logger.exception("Fee resolution failed; billing_codes proceeds with no resolved fees")
