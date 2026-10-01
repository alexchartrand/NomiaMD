"""Persists one /extract call: the Encounter holding the pasted note (before the pipeline
runs), then either an extraction run with a result row per pipeline stage, or the failure.
The run id is what the review step later hands to POST /claims.

Each step opens its own short session_scope rather than taking the request's DbSession,
for the same reason as ScopedBillingContextBuilder (scoped_context.py): the pipeline in
between makes two multi-second LLM calls that must not hold a pooled connection."""

from datetime import date

from app.extraction.models import ExtractionResult
from app.intake import Channel, content_hash
from app.postgresdb import (
    Encounter,
    EncounterInput,
    EncounterRepository,
    ExtractionRepository,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionStageInput,
    session_scope,
)

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
        stages: list[ExtractionResult],
    ) -> ExtractionRun:
        """The run, and the service date the summary found if the encounter had none yet,
        in one transaction."""
        async with session_scope() as session:
            encounters = EncounterRepository(session)
            encounter = await encounters.get_for_user(encounter_id, user_id)
            if encounter is not None and encounter.service_date is None and service_date is not None:
                await encounters.set_service_date(encounter, service_date)
            return await ExtractionRepository(session).create_run(
                ExtractionRunInput(
                    user_id=user_id,
                    encounter_id=encounter_id,
                    patient_id=patient_id,
                    stages=[
                        ExtractionStageInput(task=stage.task, model=stage.model, result=stage.result.model_dump())
                        for stage in stages
                    ],
                )
            )

    async def record_failure(self, *, encounter_id: int, user_id: int, error: BaseException) -> None:
        async with session_scope() as session:
            encounters = EncounterRepository(session)
            encounter = await encounters.get_for_user(encounter_id, user_id)
            if encounter is not None:
                await encounters.record_extraction_error(encounter, f"{type(error).__name__}: {error}")


def get_extraction_recorder() -> ExtractionRecorder:
    return ExtractionRecorder()
