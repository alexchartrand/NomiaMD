"""Has this note been received before? The same note can arrive twice through one channel
(a retried webhook) or through two (the extension and a scribe).

- With an external note id: the same id and hash is a `duplicate`; the same id with a new
  hash is a `new_version` (an amended note).
- Without one: a current encounter of this physician's for the same patient, day and
  author is taken to be the same visit — a `duplicate`, whatever its text. The outcome
  carries that encounter so the caller can show it rather than drop the note silently.
- Anything else is `new`."""

from dataclasses import dataclass
from datetime import date
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
    patient_id: int | None
    service_date: date | None
    author_ref: str | None


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
        return await self._by_visit(key)

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

    async def _by_visit(self, key: DedupKey) -> DedupResult:
        if key.patient_id is None or key.service_date is None or key.author_ref is None:
            return DedupResult(DedupOutcome.NEW)
        candidates = await self._encounters.list_current_for_patient_day(
            key.user_id, key.patient_id, key.service_date
        )
        for candidate in candidates:
            if (candidate.encounter_meta or {}).get("author_ref") == key.author_ref:
                return DedupResult(DedupOutcome.DUPLICATE, candidate)
        return DedupResult(DedupOutcome.NEW)
