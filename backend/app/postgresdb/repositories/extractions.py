"""`extraction_runs` and their per-stage `extraction_results`."""

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func, select

from app.postgresdb.models import ExtractionRun, ExtractionRunResult
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ExtractionStageInput:
    task: str
    model: str
    result: dict


@dataclass
class ExtractionRunInput:
    user_id: int
    encounter_id: int
    patient_id: int
    stages: Sequence[ExtractionStageInput]


class ExtractionRepository(SessionRepository):
    async def create_run(self, data: ExtractionRunInput) -> ExtractionRun:
        """The run and every stage's result, in the caller's one transaction."""
        run = ExtractionRun(
            user_id=data.user_id,
            encounter_id=data.encounter_id,
            patient_id=data.patient_id,
        )
        self._session.add(run)
        await self._session.flush()  # populate run.id for the result rows' FK
        self._session.add_all(
            ExtractionRunResult(run_id=run.id, task=s.task, model=s.model, result_json=s.result)
            for s in data.stages
        )
        await self._session.flush()
        return run

    async def get_run_for_user(self, run_id: int, user_id: int) -> ExtractionRun | None:
        run = await self._session.get(ExtractionRun, run_id)
        if run is None or run.user_id != user_id:
            return None
        return run

    async def get_result(self, run_id: int, task: str) -> ExtractionRunResult | None:
        result = await self._session.execute(
            select(ExtractionRunResult).where(ExtractionRunResult.run_id == run_id, ExtractionRunResult.task == task)
        )
        return result.scalar_one_or_none()

    async def latest_run_ids(self, encounter_ids: Sequence[int]) -> dict[int, int]:
        """Each encounter's most recent run id, for those that have one — re-extracting
        adds a run, and only the newest is shown for review."""
        if not encounter_ids:
            return {}
        rows = await self._session.execute(
            select(ExtractionRun.encounter_id, func.max(ExtractionRun.id))
            .where(ExtractionRun.encounter_id.in_(encounter_ids))
            .group_by(ExtractionRun.encounter_id)
        )
        return {encounter_id: run_id for encounter_id, run_id in rows.all()}

    async def get_results(self, run_ids: Sequence[int], task: str) -> dict[int, ExtractionRunResult]:
        """One stage's result for each of `run_ids`, keyed by run id."""
        if not run_ids:
            return {}
        rows = await self._session.scalars(
            select(ExtractionRunResult).where(ExtractionRunResult.run_id.in_(run_ids), ExtractionRunResult.task == task)
        )
        return {row.run_id: row for row in rows.all()}
