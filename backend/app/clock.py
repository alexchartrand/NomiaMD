"""Today's date as the clinic sees it. RAMQ billing is Québec-only, so "today" is
America/Montreal's date — never the server's, which is UTC in the container: after ~20:00
Montréal time, `date.today()` there is already tomorrow. Injected as a Clock so tests can
pin the date. The zone data comes from the `tzdata` package, since slim images ship none."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

CLINIC_ZONE = ZoneInfo("America/Montreal")


class Clock(Protocol):
    def today(self) -> date: ...


class ClinicClock:
    def today(self) -> date:
        return datetime.now(CLINIC_ZONE).date()


def get_clock() -> Clock:
    """FastAPI dependency — tests override it to pin "today"."""
    return ClinicClock()


def clinic_day_bounds(day: date) -> tuple[datetime, datetime]:
    """When the clinic's `day` starts and ends, as UTC instants (end exclusive) — what a
    database timestamp, stamped in UTC, is compared against. A DST day is 23 or 25 hours."""
    start = datetime.combine(day, time.min, CLINIC_ZONE)
    end = datetime.combine(day + timedelta(days=1), time.min, CLINIC_ZONE)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
