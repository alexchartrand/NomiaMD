"""Persists one /extract call: the Encounter holding the pasted note (before the pipeline
runs), then either an extraction run with a result row per pipeline stage, or the failure.
The run id is what the review step later hands to POST /claims.

Each step opens its own short session_scope rather than taking the request's DbSession,
for the same reason as ScopedBillingContextBuilder (scoped_context.py): the pipeline in
between makes two multi-second LLM calls that must not hold a pooled connection."""

from collections.abc import Sequence
from datetime import date

from app.extraction.pipeline import PipelineResult
from app.llm.usage import LLMCallRecord
from app.intake import Channel, content_hash
from app.postgresdb import (
    Encounter,
    EncounterInput,
    EncounterRepository,
    ExtractionRepository,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionStageInput,
    LLMCallOwner,
    LLMCallRepository,
    RunSettingInput,
    session_scope,
)
from app.ramq_codes import CodeSelector
from app.summary import ConsultationSummarizer

# TranscriptSource.system when the request doesn't say.
DEFAULT_SOURCE_SYSTEM = "manual"


class ExtractionRecorder:
    async def open_encounter(
        self,
        *,
        note_text: str,
        source_system: str | None,
        external_encounter_id: str | None,
        user_id: int,
        patient_id: int,
    ) -> Encounter:
        """A pasted note has no external note id, so it's never deduplicated: every
        /extract call is its own encounter."""
        async with session_scope() as session:
            return await EncounterRepository(session).create(
                EncounterInput(
                    user_id=user_id,
                    patient_id=patient_id,
                    source_system=source_system or DEFAULT_SOURCE_SYSTEM,
                    channel=Channel.PASTE,
                    external_encounter_id=external_encounter_id,
                    content_hash=content_hash(note_text),
                    note_text=note_text,
                )
            )

    async def save(
        self,
        *,
        encounter_id: int,
        user_id: int,
        patient_id: int,
        service_date: date | None,
        result: PipelineResult,
        llm_calls: Sequence[LLMCallRecord] = (),
        setting: RunSettingInput = RunSettingInput(),
    ) -> ExtractionRun:
        """The run, one stored stage per LLM step, the metered calls that produced it, and the
        service date the summary found if the encounter had none yet, in one transaction.
        `setting`: where the run took the encounter to be (unknown by default)."""
        async with session_scope() as session:
            encounters = EncounterRepository(session)
            encounter = await encounters.get_for_user(encounter_id, user_id)
            if encounter is not None and encounter.service_date is None and service_date is not None:
                await encounters.set_service_date(encounter, service_date)
            run = await ExtractionRepository(session).create_run(
                ExtractionRunInput(
                    user_id=user_id,
                    encounter_id=encounter_id,
                    patient_id=patient_id,
                    stages=[
                        ExtractionStageInput(
                            task=ConsultationSummarizer.NAME,
                            model=result.summary_model,
                            result=result.summary.model_dump(),
                        ),
                        ExtractionStageInput(
                            task=CodeSelector.NAME, model=result.billing_model, result=result.billing.model_dump()
                        ),
                    ],
                    setting=setting,
                )
            )
            await LLMCallRepository(session).add_many(
                llm_calls, LLMCallOwner(user_id=user_id, encounter_id=encounter_id, run_id=run.id)
            )
            return run

    async def record_failure(
        self,
        *,
        encounter_id: int,
        user_id: int,
        error: BaseException,
        llm_calls: Sequence[LLMCallRecord] = (),
    ) -> None:
        """The error on the encounter, plus the calls made before it — a failed extraction
        still spent them."""
        async with session_scope() as session:
            encounters = EncounterRepository(session)
            encounter = await encounters.get_for_user(encounter_id, user_id)
            if encounter is not None:
                await encounters.record_extraction_error(encounter, f"{type(error).__name__}: {error}")
            await LLMCallRepository(session).add_many(
                llm_calls, LLMCallOwner(user_id=user_id, encounter_id=encounter_id if encounter else None)
            )


def get_extraction_recorder() -> ExtractionRecorder:
    return ExtractionRecorder()
