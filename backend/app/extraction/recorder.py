"""Persists one /extract call as an extraction run with a result row per pipeline stage —
the run id is what the review step later hands to POST /claims.

Opens its own short session_scope rather than taking the request's DbSession, for the same
reason as ScopedBillingContextBuilder (scoped_context.py): it runs after two multi-second
LLM calls that must not hold a pooled connection."""

from app.extraction.models import ExtractionResult
from app.postgresdb import (
    ExtractionRepository,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionStageInput,
    session_scope,
)


class ExtractionRecorder:
    async def save(
        self,
        *,
        transcript: str,
        source_system: str | None,
        user_id: int,
        patient_id: int,
        stages: list[ExtractionResult],
    ) -> ExtractionRun:
        async with session_scope() as session:
            return await ExtractionRepository(session).create_run(
                ExtractionRunInput(
                    user_id=user_id,
                    patient_id=patient_id,
                    transcript=transcript,
                    source_system=source_system,
                    stages=[
                        ExtractionStageInput(task=stage.task, model=stage.model, result=stage.result.model_dump())
                        for stage in stages
                    ],
                )
            )


def get_extraction_recorder() -> ExtractionRecorder:
    return ExtractionRecorder()
