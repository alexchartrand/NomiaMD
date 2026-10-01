"""Today's date as the clinic sees it. RAMQ billing is Québec-only, so "today" is
America/Montreal's date — never the server's, which is UTC in the container: after ~20:00
Montréal time, `date.today()` there is already tomorrow. Injected as a Clock so tests can
pin the date. The zone data comes from the `tzdata` package, since slim images ship none."""

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def today(self) -> date: ...


class ClinicClock:
    _ZONE = ZoneInfo("America/Montreal")

    def today(self) -> date:
        return datetime.now(self._ZONE).date()
