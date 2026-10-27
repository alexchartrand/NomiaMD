"""Which of the physician's shifts an encounter took place during, when they didn't say. A
suggestion derived from the encounter's date and time each time it's read, never stored —
same pattern as the "doublon possible" flag (app/intake/visit_match.py): only the
physician's own pick is (Encounter.shift_id).

With a start time, the shift whose hours contain it; without one, every shift that overlaps
the service date. Exactly one is a match; several leave the choice to the physician."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from app.postgresdb import Shift
from app.shifts.periods import ShiftHours


class ShiftMatchOutcome(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


@dataclass(frozen=True)
class ShiftMatch:
    outcome: ShiftMatchOutcome
    # The shifts the encounter may belong to: one when matched, several when ambiguous.
    candidates: list[Shift] = field(default_factory=list)

    @property
    def shift(self) -> Shift | None:
        return self.candidates[0] if self.outcome == ShiftMatchOutcome.MATCHED else None


def _hours(shift: Shift) -> ShiftHours:
    return ShiftHours(shift.service_date, shift.start_time, shift.end_time)


class ShiftMatcher:
    def match(self, service_date: date | None, start_time: time | None, shifts: Sequence[Shift]) -> ShiftMatch:
        """`shifts`: the physician's live shifts around the date (the day before included, for
        a night that started then)."""
        if service_date is None:
            return ShiftMatch(ShiftMatchOutcome.NONE)
        if start_time is not None:
            candidates = self._containing(datetime.combine(service_date, start_time), shifts)
        else:
            candidates = self.overlapping(service_date, shifts)
        if not candidates:
            return ShiftMatch(ShiftMatchOutcome.NONE)
        outcome = ShiftMatchOutcome.MATCHED if len(candidates) == 1 else ShiftMatchOutcome.AMBIGUOUS
        return ShiftMatch(outcome, candidates)

    @staticmethod
    def overlapping(day: date, shifts: Sequence[Shift]) -> list[Shift]:
        """The shifts with hours on `day`: an evening ending at midnight doesn't reach the next
        day, a night from 23:00 to 07:00 does."""
        day_start = datetime.combine(day, time())
        day_end = day_start + timedelta(days=1)
        return [s for s in shifts if _hours(s).starts_at < day_end and _hours(s).ends_at > day_start]

    @staticmethod
    def _containing(moment: datetime, shifts: Sequence[Shift]) -> list[Shift]:
        """Start included, end excluded: a visit at 16:00 belongs to the evening starting
        then, not the day ending then."""
        return [s for s in shifts if _hours(s).starts_at <= moment < _hours(s).ends_at]
