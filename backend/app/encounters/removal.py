"""Deleting an encounter the physician no longer wants (a wrong paste, a test note)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.intake import EncounterNotFoundError
from app.postgresdb import EncounterRepository


class EncounterHasClaimError(ValueError):
    """The encounter has a live claim: deleting it would orphan the billing, so the physician
    voids that claim first."""


class EncounterRemoval:
    """Deletes one of the physician's own encounters, with its runs. Works in the session
    it's given."""

    def __init__(self, session: AsyncSession) -> None:
        self._encounters = EncounterRepository(session)

    async def remove(self, encounter_id: int, user_id: int) -> None:
        activity = await self._encounters.activity_for_user(encounter_id, user_id)
        if activity is None:
            raise EncounterNotFoundError(encounter_id)
        if activity.has_live_claim:
            raise EncounterHasClaimError()
        await self._encounters.delete(activity.encounter)
