"""`shifts` — a physician's blocks of work at their sites."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.postgresdb.models import Shift, ShiftSeries
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ShiftInput:
    work_site_id: int
    care_setting: str
    period: str
    service_date: date
    start_time: time
    end_time: time


class ShiftRepository(SessionRepository):
    """Stores shifts. Every read is scoped to its owner; voided shifts are invisible."""

    async def new_series(self, user_id: int) -> int:
        series = ShiftSeries(user_id=user_id)
        self._session.add(series)
        await self._session.flush()
        return series.id

    async def create(self, user_id: int, data: ShiftInput, series_id: int | None = None) -> Shift:
        shift = Shift(user_id=user_id, series_id=series_id, **vars(data))
        self._session.add(shift)
        await self._session.flush()
        return shift

    async def update(self, shift: Shift, data: ShiftInput) -> Shift:
        for field, value in vars(data).items():
            setattr(shift, field, value)
        await self._session.flush()
        return shift

    async def list_between(self, user_id: int, start: date, end: date) -> list[Shift]:
        """Shifts starting from `start` to `end`, both included."""
        result = await self._session.execute(
            select(Shift)
            .where(
                Shift.user_id == user_id,
                Shift.voided_at.is_(None),
                Shift.service_date >= start,
                Shift.service_date <= end,
            )
            .order_by(Shift.service_date, Shift.start_time, Shift.id)
        )
        return list(result.scalars().all())

    async def list_in_series(self, user_id: int, series_id: int, from_date: date | None = None) -> list[Shift]:
        """The series' live shifts — from `from_date` on (included) when given."""
        query = select(Shift).where(
            Shift.user_id == user_id,
            Shift.series_id == series_id,
            Shift.voided_at.is_(None),
        )
        if from_date is not None:
            query = query.where(Shift.service_date >= from_date)
        result = await self._session.execute(query.order_by(Shift.service_date, Shift.id))
        return list(result.scalars().all())

    async def get_for_user(self, shift_id: int, user_id: int) -> Shift | None:
        shift = await self._session.get(Shift, shift_id)
        if shift is None or shift.user_id != user_id or shift.voided_at is not None:
            return None
        return shift

    async def get_many_for_user(self, shift_ids: Sequence[int], user_id: int) -> list[Shift]:
        """Those of `shift_ids` that are the user's live shifts; the others are left out."""
        if not shift_ids:
            return []
        result = await self._session.execute(
            select(Shift).where(Shift.id.in_(shift_ids), Shift.user_id == user_id, Shift.voided_at.is_(None))
        )
        return list(result.scalars().all())

    async def void(self, shift: Shift) -> None:
        shift.voided_at = datetime.now(timezone.utc)
        await self._session.flush()
