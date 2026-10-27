"""A shift's period — jour, soir or nuit — and its hours. The period is the physician's pick
(stored on the shift); the hours default from it but are theirs to edit, since every site
splits its day its own way and shift codes are paid by the hour actually worked."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum


class ShiftPeriod(StrEnum):
    JOUR = "jour"
    SOIR = "soir"
    NUIT = "nuit"


SHIFT_PERIOD_LABELS_FR = {
    ShiftPeriod.JOUR: "Jour",
    ShiftPeriod.SOIR: "Soir",
    ShiftPeriod.NUIT: "Nuit",
}


@dataclass(frozen=True)
class ShiftHours:
    """A shift's hours in the clinic's local time: the end at or before the start is the next
    day, so an end equal to the start is a full 24 hours."""

    service_date: date
    start_time: time
    end_time: time

    @property
    def ends_next_day(self) -> bool:
        return self.end_time <= self.start_time

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.service_date, self.start_time)

    @property
    def ends_at(self) -> datetime:
        end_date = self.service_date + timedelta(days=1) if self.ends_next_day else self.service_date
        return datetime.combine(end_date, self.end_time)

    @property
    def duration(self) -> timedelta:
        return self.ends_at - self.starts_at


@dataclass(frozen=True)
class PeriodHours:
    start_time: time
    end_time: time


# What the calendar prefills when the physician picks a period. The ER's usual three 8-hour
# shifts; soir ends at midnight (00:00 the next day).
DEFAULT_PERIOD_HOURS = {
    ShiftPeriod.JOUR: PeriodHours(time(8, 0), time(16, 0)),
    ShiftPeriod.SOIR: PeriodHours(time(16, 0), time(0, 0)),
    ShiftPeriod.NUIT: PeriodHours(time(0, 0), time(8, 0)),
}
