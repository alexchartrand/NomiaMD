"""`encounters` — one signed note from one source (see the Encounter model)."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError

from app.postgresdb.models import Claim, Encounter, ExtractionRun
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class EncounterInput:
    user_id: int
    patient_id: int | None
    source_system: str
    channel: str
    content_hash: str
    note_text: str
    external_note_id: str | None = None
    external_encounter_id: str | None = None
    service_date: date | None = None
    encounter_meta: dict | None = None


@dataclass
class EncounterActivity:
    """An encounter plus the joined facts its derived status needs (app/intake/status.py)."""

    encounter: Encounter
    has_run: bool
    has_live_claim: bool


@dataclass(frozen=True)
class ReceivedWindow:
    """When a day starts and ends, as instants: an undated encounter belongs to the day it
    was received on, and that day is the clinic's (app/clock.py), not the database's."""

    start: datetime
    end: datetime


class DuplicateEncounterError(Exception):
    """This exact version of an external note (same source, note id and content hash) was
    already received — the partial unique index ix_encounters_external_version is the
    backstop for two deliveries racing past a caller's own lookup. The session can only be
    rolled back afterwards, which its owner does as this propagates (see session.py)."""


def _violates_external_version_unique(exc: IntegrityError) -> bool:
    # Same reasoning as claims.py's _violates_extraction_unique: no portable error code, so
    # match the message. SQLite names the columns, Postgres the index.
    message = str(exc.orig).lower()
    return "unique constraint" in message and (
        "ix_encounters_external_version" in message or "encounters.external_note_id" in message
    )


def _activity_columns():
    """An encounter plus the two facts app/intake/status.py derives its status from."""
    has_run = exists().where(ExtractionRun.encounter_id == Encounter.id)
    has_live_claim = exists().where(
        ExtractionRun.encounter_id == Encounter.id,
        Claim.extraction_run_id == ExtractionRun.id,
        Claim.voided_at.is_(None),
    )
    return Encounter, has_run.label("has_run"), has_live_claim.label("has_live_claim")


class EncounterRepository(SessionRepository):
    async def create(self, data: EncounterInput) -> Encounter:
        encounter = Encounter(
            user_id=data.user_id,
            patient_id=data.patient_id,
            source_system=data.source_system,
            channel=data.channel,
            external_note_id=data.external_note_id,
            external_encounter_id=data.external_encounter_id,
            content_hash=data.content_hash,
            service_date=data.service_date,
            encounter_meta=data.encounter_meta,
            note_text=data.note_text,
        )
        self._session.add(encounter)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _violates_external_version_unique(exc):
                raise DuplicateEncounterError() from exc
            raise
        return encounter

    async def get(self, encounter_id: int) -> Encounter | None:
        """Unscoped — for background work that only has the id (app/intake/queue.py). Anything
        acting on a physician's behalf uses get_for_user."""
        return await self._session.get(Encounter, encounter_id)

    async def get_for_user(self, encounter_id: int, user_id: int) -> Encounter | None:
        encounter = await self._session.get(Encounter, encounter_id)
        if encounter is None or encounter.user_id != user_id:
            return None
        return encounter

    async def list_for_day(self, user_id: int, day: date, received: ReceivedWindow) -> list[EncounterActivity]:
        """Every encounter of `day`, in arrival order, with what its status needs — one
        query, not one per encounter. An encounter with no service date yet (a paste with
        no date, still waiting for a patient or for extraction to find one) shows on the day
        it was received, so it never drops out of the inbox."""
        dated = Encounter.service_date == day
        undated = and_(
            Encounter.service_date.is_(None),
            Encounter.created_at >= received.start,
            Encounter.created_at < received.end,
        )
        return await self._activities(
            select(*_activity_columns()).where(Encounter.user_id == user_id, or_(dated, undated)).order_by(Encounter.id)
        )

    async def activity_for_user(self, encounter_id: int, user_id: int) -> EncounterActivity | None:
        activities = await self._activities(
            select(*_activity_columns()).where(Encounter.id == encounter_id, Encounter.user_id == user_id)
        )
        return activities[0] if activities else None

    async def _activities(self, query) -> list[EncounterActivity]:
        rows = await self._session.execute(query)
        return [
            EncounterActivity(encounter=encounter, has_run=bool(run), has_live_claim=bool(claim))
            for encounter, run, claim in rows.all()
        ]

    async def find_by_external(
        self, user_id: int, source_system: str, external_note_id: str, content_hash: str | None = None
    ) -> Encounter | None:
        """With `content_hash`: that exact version, if already received. Without: the
        note's current version (the newest one not superseded)."""
        query = select(Encounter).where(
            Encounter.user_id == user_id,
            Encounter.source_system == source_system,
            Encounter.external_note_id == external_note_id,
        )
        if content_hash is not None:
            query = query.where(Encounter.content_hash == content_hash)
        else:
            query = query.where(Encounter.superseded_by_id.is_(None))
        return (await self._session.scalars(query.order_by(Encounter.id.desc()).limit(1))).first()

    async def find_by_content_hash(self, user_id: int, content_hash: str) -> Encounter | None:
        """This physician's earliest encounter with exactly this note text, from any source
        — app/intake/deduplicator.py's match when a note has no external id."""
        query = (
            select(Encounter)
            .where(Encounter.user_id == user_id, Encounter.content_hash == content_hash)
            .order_by(Encounter.id)
            .limit(1)
        )
        return (await self._session.scalars(query)).first()

    async def set_patient(self, encounter: Encounter, patient_id: int) -> None:
        encounter.patient_id = patient_id
        await self._session.flush()

    async def set_service_date(self, encounter: Encounter, service_date: date) -> None:
        encounter.service_date = service_date
        await self._session.flush()

    async def mark_superseded(self, encounter: Encounter, superseded_by: Encounter) -> None:
        encounter.superseded_by_id = superseded_by.id
        await self._session.flush()

    async def record_extraction_error(self, encounter: Encounter, error: str) -> None:
        encounter.extraction_error = error
        await self._session.flush()
