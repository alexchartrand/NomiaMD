"""Where and when a physician works: their work sites (each with a care setting) and the
shifts they schedule on them — jour, soir or nuit, with the hours actually worked and the
day type (semaine, fin de semaine, férié) derived from the date.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory directly."""

from app.shifts.day_type import DAY_TYPE_LABELS_FR, DayType, DayTypeResolver
from app.shifts.periods import SHIFT_PERIOD_LABELS_FR, ShiftHours, ShiftPeriod
from app.shifts.router import shifts_router, work_sites_router

__all__ = [
    "DAY_TYPE_LABELS_FR",
    "DayType",
    "DayTypeResolver",
    "SHIFT_PERIOD_LABELS_FR",
    "ShiftHours",
    "ShiftPeriod",
    "shifts_router",
    "work_sites_router",
]
