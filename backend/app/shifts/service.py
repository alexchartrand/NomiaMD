"""Work site and shift use cases: what a physician may schedule, and where."""

from datetime import date, timedelta

from app.postgresdb import (
    Shift,
    ShiftInput,
    ShiftRepository,
    WorkSite,
    WorkSiteInput,
    WorkSiteRepository,
)
from app.shifts.day_type import DayTypeResolver
from app.shifts.models import ShiftIn, ShiftOut, WorkSiteIn, WorkSiteOut
from app.shifts.periods import ShiftHours

# The calendar shows a month at most (plus the days of the weeks it starts and ends in).
MAX_RANGE = timedelta(days=62)


class SiteUnavailableError(Exception):
    """The shift's site isn't one of the physician's active sites."""


class RangeTooLongError(Exception):
    pass


def _site_out(site: WorkSite) -> WorkSiteOut:
    return WorkSiteOut(
        id=site.id,
        name=site.name,
        care_setting=site.care_setting,
        etablissement_number=site.etablissement_number,
        is_active=site.is_active,
    )


class WorkSiteService:
    def __init__(self, sites: WorkSiteRepository) -> None:
        self._sites = sites

    async def list(self, user_id: int, *, include_inactive: bool) -> list[WorkSiteOut]:
        sites = await self._sites.list_for_user(user_id, include_inactive=include_inactive)
        return [_site_out(site) for site in sites]

    async def create(self, user_id: int, body: WorkSiteIn) -> WorkSiteOut:
        return _site_out(await self._sites.create(user_id, self._input(body)))

    async def update(self, user_id: int, site_id: int, body: WorkSiteIn) -> WorkSiteOut | None:
        """Shifts already on the site keep the care setting they were saved with."""
        site = await self._sites.get_for_user(site_id, user_id)
        if site is None:
            return None
        return _site_out(await self._sites.update(site, self._input(body)))

    async def set_active(self, user_id: int, site_id: int, active: bool) -> WorkSiteOut | None:
        site = await self._sites.get_for_user(site_id, user_id)
        if site is None:
            return None
        if active:
            await self._sites.reactivate(site)
        else:
            await self._sites.deactivate(site)
        return _site_out(site)

    @staticmethod
    def _input(body: WorkSiteIn) -> WorkSiteInput:
        return WorkSiteInput(
            name=body.name,
            care_setting=body.care_setting.value,
            etablissement_number=body.etablissement_number,
        )


class ShiftService:
    def __init__(
        self,
        shifts: ShiftRepository,
        sites: WorkSiteRepository,
        day_types: DayTypeResolver | None = None,
    ) -> None:
        self._shifts = shifts
        self._sites = sites
        self._day_types = day_types or DayTypeResolver()

    async def list_between(self, user_id: int, start: date, end: date) -> list[ShiftOut]:
        if end < start or end - start > MAX_RANGE:
            raise RangeTooLongError
        shifts = await self._shifts.list_between(user_id, start, end)
        # Deactivated sites too: their past shifts still show.
        sites = {site.id: site for site in await self._sites.list_for_user(user_id, include_inactive=True)}
        return [self._out(shift, sites[shift.work_site_id]) for shift in shifts]

    async def create(self, user_id: int, body: ShiftIn) -> ShiftOut:
        site = await self._sites.get_for_user(body.work_site_id, user_id)
        if site is None or not site.is_active:
            raise SiteUnavailableError
        shift = await self._shifts.create(user_id, self._input(body, site.care_setting))
        return self._out(shift, site)

    async def update(self, user_id: int, shift_id: int, body: ShiftIn) -> ShiftOut | None:
        """The care setting is re-read from the site only when the shift moves to another one:
        editing a shift's hours never reinterprets where it took place."""
        shift = await self._shifts.get_for_user(shift_id, user_id)
        if shift is None:
            return None
        site = await self._sites.get_for_user(body.work_site_id, user_id)
        if site is None:
            raise SiteUnavailableError
        if site.id != shift.work_site_id:
            if not site.is_active:
                raise SiteUnavailableError
            care_setting = site.care_setting
        else:
            care_setting = shift.care_setting
        shift = await self._shifts.update(shift, self._input(body, care_setting))
        return self._out(shift, site)

    async def void(self, user_id: int, shift_id: int) -> bool:
        shift = await self._shifts.get_for_user(shift_id, user_id)
        if shift is None:
            return False
        await self._shifts.void(shift)
        return True

    @staticmethod
    def _input(body: ShiftIn, care_setting: str) -> ShiftInput:
        return ShiftInput(
            work_site_id=body.work_site_id,
            care_setting=care_setting,
            period=body.period.value,
            service_date=body.service_date,
            start_time=body.start_time,
            end_time=body.end_time,
        )

    def _out(self, shift: Shift, site: WorkSite) -> ShiftOut:
        hours = ShiftHours(shift.service_date, shift.start_time, shift.end_time)
        return ShiftOut(
            id=shift.id,
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
