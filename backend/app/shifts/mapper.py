"""A stored shift as the API shows it: with its site's name, whether it ends the next day,
and the day type of its date."""

from app.postgresdb import Shift, WorkSite
from app.shifts.day_type import DayTypeResolver
from app.shifts.models import ShiftOut
from app.shifts.periods import ShiftHours


class ShiftMapper:
    def __init__(self, day_types: DayTypeResolver | None = None) -> None:
        self._day_types = day_types or DayTypeResolver()

    def out(self, shift: Shift, site: WorkSite) -> ShiftOut:
        hours = ShiftHours(shift.service_date, shift.start_time, shift.end_time)
        return ShiftOut(
            id=shift.id,
            series_id=shift.series_id,
            work_site_id=site.id,
            work_site_name=site.name,
            care_setting=shift.care_setting,
            period=shift.period,
            service_date=shift.service_date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            ends_next_day=hours.ends_next_day,
            day_type=self._day_types.day_type(shift.service_date),
        )
