"""`extraction_records` — one stored LLM extraction run per task."""

from dataclasses import dataclass
from typing import Sequence

from app.postgresdb.models import ExtractionRecord
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ExtractionRecordInput:
    task: str
    transcript: str
    result: dict
    model: str
    source_system: str | None
    user_id: int


class ExtractionRepository(SessionRepository):
    async def create_many(
        self, records: Sequence[ExtractionRecordInput]
    ) -> list[ExtractionRecord]:
        created = [
            ExtractionRecord(
                task=r.task,
                transcript=r.transcript,
                result_json=r.result,
                model=r.model,
                source_system=r.source_system,
                user_id=r.user_id,
            )
            for r in records
        ]
        self._session.add_all(created)
        await self._session.flush()
        for record in created:
            await self._session.refresh(record)
        return created

    async def get_for_user(self, record_id: int, user_id: int) -> ExtractionRecord | None:
        record = await self._session.get(ExtractionRecord, record_id)
        if record is None or record.user_id != user_id:
            return None
        return record
