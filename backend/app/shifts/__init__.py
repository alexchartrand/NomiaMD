"""Where and when a physician works: their work sites (each with a care setting) and the
shifts they schedule on them — jour, soir or nuit, with the hours actually worked and the
day type (semaine, fin de semaine, férié) derived from the date.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory directly."""

from app.shifts.day_type import DAY_TYPE_LABELS_FR, DayType, DayTypeResolver
from app.shifts.encounter_setting import EncounterSetting, EncounterSettingResolver, RunSettingSnapshot
from app.shifts.mapper import ShiftMapper
from app.shifts.matching import ShiftMatch, ShiftMatcher, ShiftMatchOutcome
from app.shifts.models import ShiftOut
from app.shifts.periods import DEFAULT_PERIOD_HOURS, SHIFT_PERIOD_LABELS_FR, ShiftHours, ShiftPeriod
from app.shifts.router import shifts_router, work_sites_router

__all__ = [
    "DEFAULT_PERIOD_HOURS",
    "DAY_TYPE_LABELS_FR",
    "DayType",
    "DayTypeResolver",
    "EncounterSetting",
    "EncounterSettingResolver",
    "RunSettingSnapshot",
    "SHIFT_PERIOD_LABELS_FR",
    "ShiftHours",
    "ShiftMapper",
    "ShiftMatch",
    "ShiftMatchOutcome",
    "ShiftMatcher",
    "ShiftOut",
    "ShiftPeriod",
    "shifts_router",
    "work_sites_router",
]
