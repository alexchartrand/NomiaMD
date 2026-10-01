""""Doublon possible": the same visit received twice with different text (e.g. the
extension's capture and the scribe's note). Intake never merges those on its own; the inbox
flags the pair and the physician answers. The flag is derived from the encounters each time
(DuplicateFlagger); only the physician's answer is stored (DuplicateDecisions)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.intake import EncounterNotFoundError, SameVisitMatcher
from app.postgresdb import Encounter, EncounterRepository


class SameEncounterError(ValueError):
    """An encounter can't be a duplicate of itself."""


class DuplicateAlreadyBilledError(ValueError):
    """The encounter to hide already has a live claim: hiding it wouldn't un-bill it, so the
    physician voids that claim first, or keeps this one instead."""


class KeptEncounterIsDuplicateError(ValueError):
    """The encounter to keep is itself hidden as another's duplicate — keep that one."""


class DuplicateFlagger:
    def __init__(self, matcher: SameVisitMatcher | None = None) -> None:
        self._matcher = matcher or SameVisitMatcher()

    def flags(self, encounters: Sequence[Encounter]) -> dict[int, list[int]]:
        """Encounter id -> the ids it may be the same visit as, for every flagged one. A
        pair is flagged only while neither side has been answered for, and while both are
        their note's current version (an amended note matches its own old version)."""
        open_ = [e for e in encounters if _unanswered(e)]
        flagged: dict[int, list[int]] = {}
        for i, a in enumerate(open_):
            for b in open_[i + 1 :]:
                if self._matcher.may_be_same_visit(a, b):
                    flagged.setdefault(a.id, []).append(b.id)
                    flagged.setdefault(b.id, []).append(a.id)
        return flagged


def _unanswered(encounter: Encounter) -> bool:
    return (
        encounter.duplicate_of_id is None
        and encounter.duplicate_dismissed_at is None
        and encounter.superseded_by_id is None
    )


class DuplicateDecisions:
    """The physician's answer to a flag, on their own encounters only. Works in the session
    it's given."""

    def __init__(self, session: AsyncSession) -> None:
        self._encounters = EncounterRepository(session)

    async def confirm(self, encounter_id: int, kept_id: int, user_id: int) -> None:
        """Same visit: `encounter_id` is hidden from the inbox and its extraction isn't
        billed; `kept_id` stays."""
        if encounter_id == kept_id:
            raise SameEncounterError()
        hidden = await self._encounters.activity_for_user(encounter_id, user_id)
        kept = await self._encounters.get_for_user(kept_id, user_id)
        if hidden is None or kept is None:
            raise EncounterNotFoundError(encounter_id if hidden is None else kept_id)
        if kept.duplicate_of_id is not None:
            raise KeptEncounterIsDuplicateError()
        if hidden.has_live_claim:
            raise DuplicateAlreadyBilledError()
        await self._encounters.mark_duplicate_of(hidden.encounter, kept)

    async def dismiss(self, encounter_id: int, user_id: int) -> None:
        """Distinct visits: this encounter is never flagged again."""
        encounter = await self._encounters.get_for_user(encounter_id, user_id)
        if encounter is None:
            raise EncounterNotFoundError(encounter_id)
        await self._encounters.dismiss_duplicate(encounter)
