"""`shifts` — a physician's blocks of work at their sites."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.postgresdb.models import Shift
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

    async def create(self, user_id: int, data: ShiftInput) -> Shift:
        shift = Shift(user_id=user_id, **vars(data))
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

    async def get_for_user(self, shift_id: int, user_id: int) -> Shift | None:
        shift = await self._session.get(Shift, shift_id)
        if shift is None or shift.user_id != user_id or shift.voided_at is not None:
            return None
        return shift

    async def void(self, shift: Shift) -> None:
        shift.voided_at = datetime.now(timezone.utc)
        await self._session.flush()
