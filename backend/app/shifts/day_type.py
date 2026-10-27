"""Whether a day is a weekday, a weekend day or a jour férié — what RAMQ's time-based
supplements and shift codes turn on (e.g. 09791 weekday evenings vs 19953 weekends and
holidays). Derived from the date, never stored."""

from datetime import date
from enum import StrEnum

from app.shifts.holidays import QuebecHolidays

_SATURDAY = 5


class DayType(StrEnum):
    SEMAINE = "semaine"
    FIN_DE_SEMAINE = "fin_de_semaine"
    FERIE = "ferie"


DAY_TYPE_LABELS_FR = {
    DayType.SEMAINE: "jour de semaine",
    DayType.FIN_DE_SEMAINE: "fin de semaine",
    DayType.FERIE: "jour férié",
}


class DayTypeResolver:
    def __init__(self, holidays: QuebecHolidays | None = None) -> None:
        self._holidays = holidays or QuebecHolidays()

    def day_type(self, day: date) -> DayType:
        """A holiday wins over a weekend: a jour férié on a Saturday is still a jour férié."""
        if self._holidays.is_holiday(day):
            return DayType.FERIE
        if day.weekday() >= _SATURDAY:
            return DayType.FIN_DE_SEMAINE
        return DayType.SEMAINE
