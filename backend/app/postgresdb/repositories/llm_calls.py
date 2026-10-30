"""`llm_calls` — every metered LLM call worth reporting on (see the model's docstring)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.postgresdb.models import LLMCall
from app.postgresdb.repositories.base import SessionRepository

if TYPE_CHECKING:
    # Type only: persistence mustn't pull in the LLM clients' SDKs at import.
    from app.llm.usage import LLMCallRecord


@dataclass(frozen=True)
class LLMCallOwner:
    """Who and what a batch of calls was made for."""

    user_id: int | None
    encounter_id: int | None = None
    run_id: int | None = None


class LLMCallRepository(SessionRepository):
    async def add_many(self, records: Iterable["LLMCallRecord"], owner: LLMCallOwner) -> None:
        self._session.add_all(
            LLMCall(
                user_id=owner.user_id,
                encounter_id=owner.encounter_id,
                run_id=owner.run_id,
                kind=record.kind,
                provider=record.provider,
                model=record.model,
                purpose=record.purpose,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                latency_ms=round(record.latency_ms, 1),
                finish_reason=record.finish_reason,
                error=record.error,
                started_at=record.started_at,
            )
            for record in records
        )
        await self._session.flush()

    async def list_between(self, since: datetime, until: datetime) -> list[LLMCall]:
        """Calls started from `since` (included) to `until` (excluded). Aggregated by the
        caller (app/admin/usage.py) in the clinic's timezone, which SQL date functions
        can't do the same way on SQLite and Postgres."""
        result = await self._session.execute(
            select(LLMCall)
            .where(LLMCall.started_at >= since, LLMCall.started_at < until)
            .order_by(LLMCall.started_at, LLMCall.id)
        )
        return list(result.scalars())

    async def list_before(self, until: datetime) -> list[LLMCall]:
        """Calls started before `until` (excluded) — what the retention rollup folds."""
        result = await self._session.execute(
            select(LLMCall).where(LLMCall.started_at < until).order_by(LLMCall.started_at, LLMCall.id)
        )
        return list(result.scalars())

    async def count_before(self, until: datetime) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(LLMCall).where(LLMCall.started_at < until)
        )
        return result.scalar_one()

    async def delete_before(self, until: datetime) -> int:
        """The retention rollup's own operation, once the calls are folded (app/retention/llm_usage.py)."""
        # No in-session sync: SQLite's naive timestamps can't be compared in Python, and the
        # deleted calls aren't read again.
        result = await self._session.execute(
            delete(LLMCall).where(LLMCall.started_at < until).execution_options(synchronize_session=False)
        )
        return result.rowcount
