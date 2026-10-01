"""Has this note been received before? The same note can arrive twice through one channel
(a retried webhook, a double paste) or through two (the extension and a scribe).

- With an external note id: the same id and hash is a `duplicate`; the same id with a new
  hash is a `new_version` (an amended note).
- Without one: only the exact same text (same hash) already on file for this physician is a
  `duplicate`. Two different texts are never merged here, even for the same patient, day
  and author: physicians often see a patient several times a day, and a wrongly merged
  visit is a visit silently never billed. Those notes are stored, and the inbox flags pairs
  that may be the same visit (app/intake/visit_match.py) for the physician to decide.
- Anything else is `new`."""

from dataclasses import dataclass
from enum import StrEnum

from app.postgresdb import Encounter, EncounterRepository


class DedupOutcome(StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    NEW_VERSION = "new_version"


@dataclass(frozen=True)
class DedupKey:
    user_id: int
    source_system: str
    content_hash: str
    external_note_id: str | None


@dataclass(frozen=True)
class DedupResult:
    outcome: DedupOutcome
    # The encounter already on file: the duplicate itself, or the version a new one amends.
    existing: Encounter | None = None


class Deduplicator:
    def __init__(self, encounters: EncounterRepository) -> None:
        self._encounters = encounters

    async def check(self, key: DedupKey) -> DedupResult:
        if key.external_note_id is not None:
            return await self._by_external_id(key, key.external_note_id)
        return await self._by_content(key)

    async def _by_external_id(self, key: DedupKey, external_note_id: str) -> DedupResult:
        same_version = await self._encounters.find_by_external(
            key.user_id, key.source_system, external_note_id, key.content_hash
        )
        if same_version is not None:
            return DedupResult(DedupOutcome.DUPLICATE, same_version)
        current = await self._encounters.find_by_external(key.user_id, key.source_system, external_note_id)
        if current is not None:
            return DedupResult(DedupOutcome.NEW_VERSION, current)
        return DedupResult(DedupOutcome.NEW)

    async def _by_content(self, key: DedupKey) -> DedupResult:
        # Any source: the extension's capture pasted again is still the same note.
        same_text = await self._encounters.find_by_content_hash(key.user_id, key.content_hash)
        if same_text is not None:
            return DedupResult(DedupOutcome.DUPLICATE, same_text)
        return DedupResult(DedupOutcome.NEW)
