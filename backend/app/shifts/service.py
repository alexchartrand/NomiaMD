"""Work site and shift use cases: what a physician may schedule, and where."""

from datetime import date, timedelta

from app.postgresdb import (
    Shift,
    ShiftClaimRepository,
    ShiftInput,
    ShiftRepository,
    WorkSite,
    WorkSiteInput,
    WorkSiteRepository,
)
from app.shifts.mapper import ShiftMapper
from app.shifts.models import ShiftIn, ShiftOut, ShiftSeriesIn, ShiftSeriesUpdateIn, WorkSiteIn, WorkSiteOut

# The calendar shows a month at most (plus the days of the weeks it starts and ends in).
MAX_RANGE = timedelta(days=62)


class SiteUnavailableError(Exception):
    """The shift's site isn't one of the physician's active sites."""


class RangeTooLongError(Exception):
    pass


class ShiftBilledError(Exception):
    """The shift's claim is on a bill: the shift stays until that bill is voided."""


class EmptySeriesError(Exception):
    """A series whose range holds no day to schedule (only a weekend, weekdays only)."""


_SATURDAY = 5


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
        shift_claims: ShiftClaimRepository,
        mapper: ShiftMapper | None = None,
    ) -> None:
        self._shifts = shifts
        self._sites = sites
        self._shift_claims = shift_claims
        self._mapper = mapper or ShiftMapper()

    async def list_between(self, user_id: int, start: date, end: date) -> list[ShiftOut]:
        if end < start or end - start > MAX_RANGE:
            raise RangeTooLongError
        shifts = await self._shifts.list_between(user_id, start, end)
        # Deactivated sites too: their past shifts still show.
        sites = {site.id: site for site in await self._sites.list_for_user(user_id, include_inactive=True)}
        return [self._mapper.out(shift, sites[shift.work_site_id]) for shift in shifts]

    async def create(self, user_id: int, body: ShiftIn) -> ShiftOut:
        site = await self._sites.get_for_user(body.work_site_id, user_id)
        if site is None or not site.is_active:
            raise SiteUnavailableError
        shift = await self._shifts.create(user_id, self._input(body, site.care_setting))
        return self._mapper.out(shift, site)

    async def create_series(self, user_id: int, body: ShiftSeriesIn) -> list[ShiftOut]:
        """All of the series' shifts or none: they're written in the request's one transaction."""
        if body.end_date < body.start_date or body.end_date - body.start_date > MAX_RANGE:
            raise RangeTooLongError
        site = await self._sites.get_for_user(body.work_site_id, user_id)
        if site is None or not site.is_active:
            raise SiteUnavailableError
        days = [
            body.start_date + timedelta(days=offset)
            for offset in range((body.end_date - body.start_date).days + 1)
        ]
        if body.weekdays_only:
            days = [day for day in days if day.weekday() < _SATURDAY]
        if not days:
            raise EmptySeriesError
        series_id = await self._shifts.new_series(user_id)
        created = []
        for day in days:
            shift_body = ShiftIn(
                work_site_id=body.work_site_id,
                period=body.period,
                service_date=day,
                start_time=body.start_time,
                end_time=body.end_time,
            )
            shift = await self._shifts.create(user_id, self._input(shift_body, site.care_setting), series_id)
            created.append(self._mapper.out(shift, site))
        return created

    async def update(self, user_id: int, shift_id: int, body: ShiftIn) -> ShiftOut | None:
        shift = await self._shifts.get_for_user(shift_id, user_id)
        if shift is None:
            return None
        site = await self._sites.get_for_user(body.work_site_id, user_id)
        if site is None:
            raise SiteUnavailableError
        shift = await self._shifts.update(shift, self._input(body, self._care_setting_for(shift, site)))
        return self._mapper.out(shift, site)

    async def update_series(self, user_id: int, series_id: int, body: ShiftSeriesUpdateIn) -> list[ShiftOut] | None:
        """Every live shift of the series (from `body.from_date` on), each on its own date.
        None when there's none left to edit."""
        shifts = await self._shifts.list_in_series(user_id, series_id, body.from_date)
        if not shifts:
            return None
        site = await self._sites.get_for_user(body.work_site_id, user_id)
        if site is None:
            raise SiteUnavailableError
        updated = []
        for shift in shifts:
            shift_body = ShiftIn(
                work_site_id=body.work_site_id,
                period=body.period,
                service_date=shift.service_date,
                start_time=body.start_time,
                end_time=body.end_time,
            )
            shift = await self._shifts.update(shift, self._input(shift_body, self._care_setting_for(shift, site)))
            updated.append(self._mapper.out(shift, site))
        return updated

    async def void(self, user_id: int, shift_id: int) -> bool:
        shift = await self._shifts.get_for_user(shift_id, user_id)
        if shift is None:
            return False
        await self._void_with_claim(user_id, [shift])
        return True

    async def void_series(self, user_id: int, series_id: int, from_date: date | None = None) -> int:
        """Voids the series' live shifts (from `from_date` on); how many it voided. None of
        them if one is billed."""
        shifts = await self._shifts.list_in_series(user_id, series_id, from_date)
        await self._void_with_claim(user_id, shifts)
        return len(shifts)

    async def _void_with_claim(self, user_id: int, shifts: list[Shift]) -> None:
        """A shift's draft claim goes with it; a shift whose claim is on a bill can't go."""
        drafts = []
        for shift in shifts:
            claim = await self._shift_claims.live_for_shift(shift.id, user_id)
            if claim is None:
                continue
            # On a bill = "soumis" (app/claims/status.py, not imported: claims reads shifts).
            if claim.claim.bill_id is not None:
                raise ShiftBilledError
            drafts.append(claim.claim)
        for draft in drafts:
            await self._shift_claims.void(draft)
        for shift in shifts:
            await self._shifts.void(shift)

    @staticmethod
    def _care_setting_for(shift: Shift, site: WorkSite) -> str:
        """Re-read from the site only when the shift moves to another one: editing a shift's
        hours never reinterprets where it took place. A shift can't move to an archived site."""
        if site.id == shift.work_site_id:
            return shift.care_setting
        if not site.is_active:
            raise SiteUnavailableError
        return site.care_setting

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
