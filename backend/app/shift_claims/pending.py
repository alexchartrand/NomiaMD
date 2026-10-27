"""Past shifts still to claim: those whose rules earn a shift code, with no live claim yet."""

from datetime import date

from app.care_setting import parse_care_setting
from app.postgresdb import ShiftClaimRepository, ShiftRepository
from app.shift_claims.rules import ShiftCodeRules
from app.shifts import ShiftHours


class UnclaimedShifts:
    def __init__(self, shifts: ShiftRepository, claims: ShiftClaimRepository, rules: ShiftCodeRules) -> None:
        self._shifts = shifts
        self._claims = claims
        self._rules = rules

    async def count(self, user_id: int, since: date, until: date) -> int:
        """Shifts starting from `since` to `until`, both included."""
        earning = [
            shift
            for shift in await self._shifts.list_between(user_id, since, until)
            if self._rules.suggest(
                parse_care_setting(shift.care_setting),
                ShiftHours(shift.service_date, shift.start_time, shift.end_time),
            )
        ]
        claimed = await self._claims.claimed_shift_ids(user_id, [shift.id for shift in earning])
        return sum(1 for shift in earning if shift.id not in claimed)
