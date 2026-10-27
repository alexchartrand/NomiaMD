"""Which shift codes a shift earns, and for how many hours — deterministic, from the shift's
care setting, hours and the day type of each calendar day it covers. Never from a note or the
model: the physician confirms these suggestions before anything is claimed.

Each hour is read on its own day: an ER shift from Friday 18 h to Saturday 10 h earns 4 h of
09791 (Friday 20 h–24 h, a weekday) and 2 h of 19953 (Saturday 8 h–10 h)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.care_setting import CareSetting
from app.shift_claims.catalog import GardeOption, ShiftCode, ShiftCodeCatalog
from app.shifts import DayTypeResolver, ShiftHours

_MINUTES_PER_HOUR = 60


@dataclass(frozen=True)
class SuggestedShiftLine:
    code: ShiftCode
    hours: int


class ShiftCodeRules:
    def __init__(self, catalog: ShiftCodeCatalog, day_types: DayTypeResolver | None = None) -> None:
        self._catalog = catalog
        self._day_types = day_types or DayTypeResolver()

    def suggest(
        self,
        care_setting: CareSetting | None,
        hours: ShiftHours,
        garde_option: GardeOption = GardeOption.ACTE,
    ) -> list[SuggestedShiftLine]:
        """The codes the shift earns under the physician's garde option, in catalog order; a
        code it earns no billable hour of is left out — a forfait not divisible in hours needs
        its whole period. An unknown care setting earns nothing."""
        if care_setting is None:
            return []
        lines = []
        for code in self._catalog.for_care_setting(care_setting, garde_option):
            billable = self.billable_hours(code, self._minutes_in_window(code, hours))
            if billable > 0:
                lines.append(SuggestedShiftLine(code=code, hours=billable))
        # A code that excludes others wins over them: 09996, the forfait the physician chose,
        # over the 09791/19953 supplements.
        excluded = {number for line in lines for number in line.code.excludes}
        return [line for line in lines if line.code.number not in excluded]

    @staticmethod
    def billable_hours(code: ShiftCode, minutes: int) -> int:
        """Whole hours when the code is divisible in hours, else whole quarts only."""
        whole_hours = minutes // _MINUTES_PER_HOUR
        if code.divisible_in_hours:
            return whole_hours
        return whole_hours // code.quart_hours * code.quart_hours

    def _minutes_in_window(self, code: ShiftCode, hours: ShiftHours) -> int:
        # The day before too: a window running past midnight reaches into a shift starting at 0 h.
        first = hours.service_date - timedelta(days=1)
        last = hours.ends_at.date()
        total = 0
        day = first
        while day <= last:
            if self._day_types.day_type(day) in code.day_types:
                start, end = self._window_on(code, day)
                total += _overlap_minutes(start, end, hours.starts_at, hours.ends_at)
            day += timedelta(days=1)
        return total

    @staticmethod
    def _window_on(code: ShiftCode, day: date) -> tuple[datetime, datetime]:
        window = code.window
        start = datetime.combine(day, window.start)
        end_day = day + timedelta(days=1) if window.end <= window.start else day
        return start, datetime.combine(end_day, window.end)


def _overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    overlap = min(a_end, b_end) - max(a_start, b_start)
    return max(0, int(overlap.total_seconds() // 60))
