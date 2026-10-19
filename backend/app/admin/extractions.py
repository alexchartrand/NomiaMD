"""Failed extractions across every physician, and re-queuing one — the admin console's
counterpart to the inbox's own "réessayer", for when a provider outage failed a batch."""

from dataclasses import dataclass

from app.audit import AuditAction, AuditEntry, IAuditLog
from app.intake.queue import ExtractionQueue
from app.postgresdb import EncounterRepository, FailedExtraction, User, UserRepository


class EncounterNotRetryableError(Exception):
    """No such encounter, or it has no patient yet (nothing to extract against)."""


@dataclass(frozen=True)
class FailedExtractionList:
    failures: list[FailedExtraction]
    physician_names: dict[int, str]


class FailedExtractions:
    def __init__(self, encounters: EncounterRepository, users: UserRepository, audit_log: IAuditLog) -> None:
        self._encounters = encounters
        self._users = users
        self._audit = audit_log

    async def list(self, *, limit: int = 100) -> FailedExtractionList:
        failures = await self._encounters.list_failed_extractions(limit=limit)
        names = {u.id: u.full_name for u in await self._users.list_all()}
        return FailedExtractionList(failures, names)

    async def retry(self, actor: User, encounter_id: int, queue: ExtractionQueue) -> None:
        encounter = await self._encounters.get(encounter_id)
        if encounter is None or encounter.patient_id is None:
            raise EncounterNotRetryableError(encounter_id)
        # Queued before the audit row is written: the inline queue (no Redis) runs the whole
        # extraction inside enqueue, in its own sessions, which must not wait on a write lock
        # this request's session already holds (SQLite).
        await queue.enqueue(encounter_id)
        await self._audit.record(
            AuditEntry(
                AuditAction.EXTRACTION_RETRIED,
                actor_id=actor.id,
                target_user_id=encounter.user_id,
                details={"encounter_id": encounter_id},
            )
        )
