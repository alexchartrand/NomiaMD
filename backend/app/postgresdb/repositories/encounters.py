"""`encounters` — one signed note from one source (see the Encounter model)."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased
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
    """When a period starts and ends, as instants (end exclusive; None = unbounded): an
    undated encounter belongs to the day it was received on, and that day is the clinic's
    (app/clock.py), not the database's."""

    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class EncounterPeriod:
    """Service dates `first` through `last`, both included (None = unbounded), and the same
    period as instants for the undated encounters."""

    first: date | None
    last: date | None
    received: ReceivedWindow


@dataclass(frozen=True)
class OverviewScope:
    """What a summary of the physician's work needs, without reading their whole history:
    `window`'s encounters plus the `latest` received ones, and — however old — every one
    still unsettled or that may be another's duplicate (see list_for_overview)."""

    window: EncounterPeriod
    latest: int


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


def _has_run():
    return exists().where(ExtractionRun.encounter_id == Encounter.id)


def _has_live_claim():
    return exists().where(
        ExtractionRun.encounter_id == Encounter.id,
        Claim.extraction_run_id == ExtractionRun.id,
        Claim.voided_at.is_(None),
    )


def _activity_columns():
    """An encounter plus the two facts app/intake/status.py derives its status from."""
    return Encounter, _has_run().label("has_run"), _has_live_claim().label("has_live_claim")


def _in_period(period: EncounterPeriod):
    """Dated encounters by service date, undated ones by when they were received."""
    dated = [Encounter.service_date.is_not(None)]
    if period.first is not None:
        dated.append(Encounter.service_date >= period.first)
    if period.last is not None:
        dated.append(Encounter.service_date <= period.last)
    undated = [Encounter.service_date.is_(None)]
    if period.received.start is not None:
        undated.append(Encounter.created_at >= period.received.start)
    if period.received.end is not None:
        undated.append(Encounter.created_at < period.received.end)
    return or_(and_(*dated), and_(*undated))


def _is_open(encounter):
    """Not answered for as a duplicate, and its note's current version (DuplicateFlagger's
    candidates)."""
    return and_(
        encounter.duplicate_of_id.is_(None),
        encounter.duplicate_dismissed_at.is_(None),
        encounter.superseded_by_id.is_(None),
    )


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

    async def list_in_period(self, user_id: int, period: EncounterPeriod) -> list[EncounterActivity]:
        """Every encounter of the period, in arrival order, with what its status needs — one
        query, not one per encounter. An encounter with no service date yet (a paste with
        no date, still waiting for a patient or for extraction to find one) belongs to the
        day it was received, so it never drops out of the inbox. One confirmed as another's
        duplicate is left out."""
        return await self._activities(
            select(*_activity_columns())
            .where(Encounter.user_id == user_id, Encounter.duplicate_of_id.is_(None), _in_period(period))
            .order_by(Encounter.id)
        )

    async def list_for_overview(self, user_id: int, scope: OverviewScope) -> list[EncounterActivity]:
        """The encounters a summary can't do without, in arrival order, one query. Besides
        the window and the latest received, at any age:

        - unsettled ones — not superseded, and not billed once matched to a patient: every
          encounter app/intake/status.py could call anything but `modifié` or `revu`;
        - open ones sharing a patient and a service date with another open one — a superset
          of the pairs DuplicateFlagger can flag, so its flags over this list are exact.

        Confirmed duplicates are left out, as in list_in_period."""
        latest = (
            select(Encounter.id)
            .where(Encounter.user_id == user_id, Encounter.duplicate_of_id.is_(None))
            .order_by(Encounter.created_at.desc(), Encounter.id.desc())
            .limit(scope.latest)
        )
        unsettled = and_(
            Encounter.superseded_by_id.is_(None),
            or_(Encounter.patient_id.is_(None), ~_has_live_claim()),
        )
        other = aliased(Encounter)
        shares_a_visit = and_(
            _is_open(Encounter),
            exists().where(
                other.user_id == Encounter.user_id,
                other.id != Encounter.id,
                other.patient_id == Encounter.patient_id,
                other.service_date == Encounter.service_date,
                _is_open(other),
            ),
        )
        return await self._activities(
            select(*_activity_columns())
            .where(
                Encounter.user_id == user_id,
                Encounter.duplicate_of_id.is_(None),
                or_(_in_period(scope.window), Encounter.id.in_(latest), unsettled, shares_a_visit),
            )
            .order_by(Encounter.id)
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

    async def mark_duplicate_of(self, encounter: Encounter, kept: Encounter) -> None:
        encounter.duplicate_of_id = kept.id
        await self._session.flush()

    async def dismiss_duplicate(self, encounter: Encounter) -> None:
        encounter.duplicate_dismissed_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def delete(self, encounter: Encounter) -> None:
        """Hard delete — the retention purge's own operation. Runs and results cascade; claims,
        duplicate links and amended-note links are detached (SET NULL)."""
        await self._session.delete(encounter)
        await self._session.flush()
