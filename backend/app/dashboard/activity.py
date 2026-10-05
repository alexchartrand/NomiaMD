"""Encounters per week, received vs reviewed. A week starts on Monday; an encounter counts
on its service date, or — undated — on the clinic day it was received (as the inbox groups
it)."""

from collections import Counter
from datetime import date, timedelta

from app.clock import CLINIC_ZONE
from app.dashboard.models import WeekActivityOut
from app.encounters.models import EncounterRowOut
from app.intake import EncounterStatus


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def clinic_day_of(row: EncounterRowOut) -> date:
    return row.service_date or row.received_at.astimezone(CLINIC_ZONE).date()


class WeeklyActivity:
    def __init__(self, weeks: int = 8) -> None:
        self._weeks = weeks

    def buckets(self, rows: list[EncounterRowOut], today: date) -> list[WeekActivityOut]:
        """The last `weeks` weeks, oldest first, this one included — empty weeks too."""
        received: Counter[date] = Counter()
        reviewed: Counter[date] = Counter()
        for row in rows:
            week = week_start(clinic_day_of(row))
            received[week] += 1
            if row.status == EncounterStatus.REVU:
                reviewed[week] += 1
        this_week = week_start(today)
        weeks = [this_week - timedelta(weeks=n) for n in reversed(range(self._weeks))]
        return [WeekActivityOut(week_start=w, received=received[w], reviewed=reviewed[w]) for w in weeks]
