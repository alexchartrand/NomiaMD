"""The single way a note enters NomiaMD, whatever channel it came through: normalize it,
resolve its patient, deduplicate it, store it as an Encounter, and queue its extraction
once a patient is known.

Opens its own short session_scope rather than taking the caller's: an InlineExtractionQueue
makes LLM calls, which must not hold a pooled connection (same reasoning as
app/extraction/recorder.py)."""

from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.encounter_date import DateOrder, parse_encounter_date
from app.intake.deduplicator import DedupKey, DedupOutcome, Deduplicator
from app.intake.hashing import content_hash
from app.intake.models import SourceNote
from app.intake.normalizers import NormalizerRegistry, default_normalizers
from app.intake.patient_resolver import PatientResolver
from app.intake.queue import ExtractionQueue
from app.postgresdb import (
    DuplicateEncounterError,
    Encounter,
    EncounterInput,
    EncounterRepository,
    PatientRepository,
    User,
    session_scope,
)


class EmptyNoteError(ValueError):
    """Nothing is left of the note once normalized (e.g. an HTML capture with no text)."""


@dataclass(frozen=True)
class ReceiveOutcome:
    outcome: DedupOutcome
    # The stored encounter — for a duplicate, the one already on file.
    encounter_id: int
    patient_id: int | None
    enqueued: bool


class IntakeService:
    def __init__(self, queue: ExtractionQueue, normalizers: NormalizerRegistry | None = None) -> None:
        self._queue = queue
        self._normalizers = normalizers or default_normalizers()

    async def receive(self, note: SourceNote, user: User) -> ReceiveOutcome:
        normalizer = self._normalizers.for_source(note.source_system)
        text = normalizer.normalize(note.text)
        if not text:
            raise EmptyNoteError()
        note_hash = content_hash(text)
        service_date = _service_date(note.service_date, normalizer.date_order)

        try:
            async with session_scope() as session:
                outcome = await self._store(session, note, user, text, note_hash, service_date)
        except DuplicateEncounterError:
            # Another delivery of this exact version committed between our lookup and our
            # insert; the unique index caught it, and theirs is the one on file.
            async with session_scope() as session:
                existing = await EncounterRepository(session).find_by_external(
                    user.id, note.source_system, note.external_note_id, note_hash
                )
            assert existing is not None
            return _not_stored(existing)

        # Without a patient there's no billing context to extract against: the encounter
        # waits "à associer" until the physician picks one.
        if outcome.outcome == DedupOutcome.DUPLICATE or outcome.patient_id is None:
            return outcome
        await self._queue.enqueue(outcome.encounter_id)
        return replace(outcome, enqueued=True)

    async def _store(
        self, session: AsyncSession, note: SourceNote, user: User, text: str, note_hash: str, service_date: date | None
    ) -> ReceiveOutcome:
        patient_id = await PatientResolver(PatientRepository(session)).resolve(note.nam)
        encounters = EncounterRepository(session)
        dedup = await Deduplicator(encounters).check(
            DedupKey(
                user_id=user.id,
                source_system=note.source_system,
                content_hash=note_hash,
                external_note_id=note.external_note_id,
                patient_id=patient_id,
                service_date=service_date,
                author_ref=note.meta.author_ref,
            )
        )
        if dedup.outcome == DedupOutcome.DUPLICATE:
            assert dedup.existing is not None
            return _not_stored(dedup.existing)

        # TODO(step 16): on NEW_VERSION, mark dedup.existing superseded by the new row and
        # flag any claim made from it for re-review. For now both versions stay current.
        encounter = await encounters.create(
            EncounterInput(
                user_id=user.id,
                patient_id=patient_id,
                source_system=note.source_system,
                channel=note.channel,
                content_hash=note_hash,
                note_text=text,
                external_note_id=note.external_note_id,
                external_encounter_id=note.external_encounter_id,
                service_date=service_date,
                encounter_meta=_encounter_meta(note),
            )
        )
        return ReceiveOutcome(dedup.outcome, encounter.id, patient_id, enqueued=False)


def _service_date(raw: date | str | None, date_order: DateOrder) -> date | None:
    if raw is None or isinstance(raw, date):
        return raw
    return parse_encounter_date(raw, date_order)


def _encounter_meta(note: SourceNote) -> dict | None:
    """The source's structured facts, minus the ones with their own column."""
    meta = note.meta.model_dump(mode="json", exclude_none=True)
    meta |= note.model_dump(mode="json", include={"signed_at", "mrn", "batch_label"}, exclude_none=True)
    return meta or None


def _not_stored(existing: Encounter) -> ReceiveOutcome:
    return ReceiveOutcome(DedupOutcome.DUPLICATE, existing.id, existing.patient_id, enqueued=False)
