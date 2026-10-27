"""An encounter's shift and care setting as the inbox shows them (resolved by
app/shifts/encounter_setting.py), and the physician's own pick of its shift."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.encounters.models import EncounterSettingOut
from app.extraction.models import BillingExtractionResponse
from app.intake import EncounterNotFoundError
from app.postgresdb import EncounterRepository, ShiftRepository, WorkSite, WorkSiteRepository
from app.shifts import EncounterSetting, ShiftMapper


class ShiftNotFoundError(LookupError):
    """Not one of the physician's live shifts."""


def differs_from_run(setting: EncounterSetting, extraction: BillingExtractionResponse | None) -> bool:
    """The encounter's shift or care setting changed since its latest run chose its codes — or
    became known since: a run made with none (POST /extract's) records all nulls. No setting
    at all is /extract's own response, never compared."""
    if extraction is None or extraction.setting is None:
        return False
    shift_id = setting.shift.id if setting.shift is not None else None
    return extraction.setting.care_setting != setting.care_setting or extraction.setting.shift_id != shift_id


class EncounterSettingPresenter:
    """Needs the physician's sites, archived ones included: their past shifts still show."""

    def __init__(self, sites: list[WorkSite], mapper: ShiftMapper | None = None) -> None:
        self._sites = {site.id: site for site in sites}
        self._mapper = mapper or ShiftMapper()

    @classmethod
    async def for_user(cls, session: AsyncSession, user_id: int) -> "EncounterSettingPresenter":
        return cls(await WorkSiteRepository(session).list_for_user(user_id, include_inactive=True))

    def out(self, setting: EncounterSetting, extraction: BillingExtractionResponse | None) -> EncounterSettingOut:
        shift = setting.shift
        return EncounterSettingOut(
            care_setting=setting.care_setting,
            shift=self._mapper.out(shift, self._sites[shift.work_site_id]) if shift is not None else None,
            shift_picked=setting.picked,
            needs_shift_choice=setting.needs_shift_choice,
            differs_from_run=differs_from_run(setting, extraction),
            shift_options=[self._mapper.out(s, self._sites[s.work_site_id]) for s in setting.options],
        )


class EncounterShiftLink:
    """Works in the session it's given."""

    def __init__(self, session: AsyncSession) -> None:
        self._encounters = EncounterRepository(session)
        self._shifts = ShiftRepository(session)

    async def set(self, encounter_id: int, user_id: int, shift_id: int | None) -> None:
        """The shift the encounter took place during — any of the physician's live shifts, as
        they say. None withdraws the pick: the shift is derived again. Changes nothing already
        extracted or billed: the review offers to re-extract."""
        encounter = await self._encounters.get_for_user(encounter_id, user_id)
        if encounter is None:
            raise EncounterNotFoundError(encounter_id)
        if shift_id is not None and await self._shifts.get_for_user(shift_id, user_id) is None:
            raise ShiftNotFoundError(shift_id)
        await self._encounters.set_shift(encounter, shift_id)
