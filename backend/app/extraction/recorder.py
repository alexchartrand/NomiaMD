"""Persists both stages of one /extract run as extraction_records rows — the ids the review
step later hands to POST /claims.

Opens its own short session_scope rather than taking the request's DbSession, for the same
reason as ScopedBillingContextBuilder (scoped_context.py): it runs after two multi-second
LLM calls that must not hold a pooled connection."""

from app.extraction.models import ExtractionResult
from app.postgresdb import ExtractionRecord, ExtractionRecordInput, ExtractionRepository, session_scope


class ExtractionRecorder:
    async def save(
        self,
        *,
        transcript: str,
        source_system: str | None,
        user_id: int,
        summary: ExtractionResult,
        billing: ExtractionResult,
    ) -> tuple[ExtractionRecord, ExtractionRecord]:
        async with session_scope() as session:
            summary_record, billing_record = await ExtractionRepository(session).create_many(
                [
                    ExtractionRecordInput(
                        task=stage.task,
                        transcript=transcript,
                        result=stage.result.model_dump(),
                        model=stage.model,
                        source_system=source_system,
                        user_id=user_id,
                    )
                    for stage in (summary, billing)
                ]
            )
        return summary_record, billing_record


def get_extraction_recorder() -> ExtractionRecorder:
    return ExtractionRecorder()
