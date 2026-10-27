"""Where and during which shift an encounter took place, decided in one place, in this order:

1. the shift the physician picked for it (Encounter.shift_id), while that shift is live;
2. else the one ShiftMatcher derives from its date and time, when exactly one fits;
3. else the care setting its source sent or the physician picked at paste
   (EncounterMeta.care_setting);
4. else unknown.

A shift's care setting is the one snapshotted from its site. Like every administrative fact,
none of this ever comes from the note text."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.care_setting import CareSetting, parse_care_setting
from app.postgresdb import Encounter, RunSettingInput, Shift, ShiftRepository
from app.shifts.day_type import DayTypeResolver
from app.shifts.matching import ShiftMatcher, ShiftMatchOutcome


@dataclass(frozen=True)
class EncounterSetting:
    care_setting: CareSetting | None
    # The physician's pick, else the matched shift; None when neither.
    shift: Shift | None = None
    # `shift` is the physician's pick, not a derived match.
    picked: bool = False
    # Several shifts fit and none was picked: the physician chooses.
    needs_shift_choice: bool = False
    # What the physician may pick from: the shifts overlapping the service date, plus the
    # picked one wherever it is.
    options: list[Shift] = field(default_factory=list)


class EncounterSettingResolver:
    """Works in the session it's given; reads only the physician's own live shifts."""

    def __init__(self, session: AsyncSession, matcher: ShiftMatcher | None = None) -> None:
        self._shifts = ShiftRepository(session)
        self._matcher = matcher or ShiftMatcher()

    async def resolve(self, encounter: Encounter) -> EncounterSetting:
        return (await self.resolve_many(encounter.user_id, [encounter]))[encounter.id]

    async def resolve_many(self, user_id: int, encounters: Sequence[Encounter]) -> dict[int, EncounterSetting]:
        """Two queries whatever the number of encounters."""
        picked_ids = {e.shift_id for e in encounters if e.shift_id is not None}
        picked = {s.id: s for s in await self._shifts.get_many_for_user(list(picked_ids), user_id)}
        by_day = await self._shifts_by_day(user_id, [e.service_date for e in encounters if e.service_date])
        return {
            encounter.id: self._settle(
                encounter,
                picked.get(encounter.shift_id) if encounter.shift_id is not None else None,
                _around(by_day, encounter.service_date),
            )
            for encounter in encounters
        }

    def _settle(self, encounter: Encounter, picked: Shift | None, nearby: list[Shift]) -> EncounterSetting:
        options = self._matcher.overlapping(encounter.service_date, nearby) if encounter.service_date else []
        if picked is not None:
            if picked not in options:
                options = [picked, *options]
            return EncounterSetting(parse_care_setting(picked.care_setting), picked, picked=True, options=options)
        match = self._matcher.match(encounter.service_date, _start_time(encounter), nearby)
        if match.shift is not None:
            return EncounterSetting(parse_care_setting(match.shift.care_setting), match.shift, options=options)
        return EncounterSetting(
            parse_care_setting((encounter.encounter_meta or {}).get("care_setting")),
            needs_shift_choice=match.outcome == ShiftMatchOutcome.AMBIGUOUS,
            options=options,
        )

    async def _shifts_by_day(self, user_id: int, days: list[date]) -> dict[date, list[Shift]]:
        if not days:
            return {}
        # The day before the first too: a night that started then reaches into it.
        shifts = await self._shifts.list_between(user_id, min(days) - timedelta(days=1), max(days))
        by_day: dict[date, list[Shift]] = defaultdict(list)
        for shift in shifts:
            by_day[shift.service_date].append(shift)
        return by_day


class RunSettingSnapshot:
    """What an extraction run records of the setting it ran under (ExtractionRun's setting
    columns). The day type is the encounter's own date's when known, else its shift's."""

    def __init__(self, day_types: DayTypeResolver | None = None) -> None:
        self._day_types = day_types or DayTypeResolver()

    def of(self, setting: EncounterSetting, service_date: date | None) -> RunSettingInput:
        shift = setting.shift
        day = service_date or (shift.service_date if shift is not None else None)
        return RunSettingInput(
            care_setting=setting.care_setting.value if setting.care_setting is not None else None,
            shift_id=shift.id if shift is not None else None,
            shift_period=shift.period if shift is not None else None,
            day_type=self._day_types.day_type(day).value if day is not None else None,
        )


def _around(by_day: dict[date, list[Shift]], day: date | None) -> list[Shift]:
    if day is None:
        return []
    return [*by_day.get(day - timedelta(days=1), []), *by_day.get(day, [])]


def _start_time(encounter: Encounter) -> time | None:
    raw = (encounter.encounter_meta or {}).get("time_start")
    try:
        return time.fromisoformat(raw) if raw else None
    except ValueError:
        return None
