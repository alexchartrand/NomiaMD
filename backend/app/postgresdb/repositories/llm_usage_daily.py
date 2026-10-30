"""`llm_usage_daily` and `extraction_usage_daily` — llm_calls folded by clinic day once past
their raw retention (see the models' docstrings)."""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select

from app.postgresdb.models import ExtractionUsageDay, LLMUsageDay
from app.postgresdb.repositories.base import SessionRepository


class LLMUsageDayRepository(SessionRepository):
    async def list_between(self, first: date, last: date) -> list[LLMUsageDay]:
        """Days `first` through `last`, both included."""
        result = await self._session.scalars(
            select(LLMUsageDay)
            .where(LLMUsageDay.day >= first, LLMUsageDay.day <= last)
            .order_by(LLMUsageDay.day, LLMUsageDay.id)
        )
        return list(result)

    async def list_extractions_between(self, first: date, last: date) -> list[ExtractionUsageDay]:
        result = await self._session.scalars(
            select(ExtractionUsageDay)
            .where(ExtractionUsageDay.day >= first, ExtractionUsageDay.day <= last)
            .order_by(ExtractionUsageDay.day, ExtractionUsageDay.id)
        )
        return list(result)

    async def add_many(self, rows: Iterable[LLMUsageDay | ExtractionUsageDay]) -> None:
        """New rows, or rows read from this session and changed: both are flushed."""
        self._session.add_all(rows)
        await self._session.flush()
