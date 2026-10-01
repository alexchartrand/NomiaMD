"""PatientResolver and Deduplicator against the test DB (conftest's rolled-back
db_session) — no HTTP, no LLM."""

import itertools
from datetime import date, datetime, timezone

import pytest

from app.intake import Channel, content_hash
from app.intake.deduplicator import DedupKey, DedupOutcome, Deduplicator
from app.intake.patient_resolver import PatientResolver
from app.postgresdb import EncounterInput, EncounterRepository, Gender, PatientRepository
from tests.db_helpers import ensure_user_row, physician

_physician_ids = itertools.count(5000)
# "INTR" prefix, distinct from every other test file's — patients are globally unique by
# NAM and the test DB is shared across the whole session (see conftest.py).
_ramq_numbers = itertools.count(1)

DAY = date(2026, 3, 4)


@pytest.fixture
async def physician_id():
    user_id = next(_physician_ids)
    await ensure_user_row(physician(user_id))
    return user_id


async def _seed_patient(session):
    return await PatientRepository(session).create(
        full_name="Roch Desjardins",
        ramq_number=f"INTR{next(_ramq_numbers):08d}",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )


# --- PatientResolver ---


async def test_resolver_matches_a_registered_nam(db_session):
    patient = await _seed_patient(db_session)
    assert await PatientResolver(PatientRepository(db_session)).resolve(patient.ramq_number) == patient.id


async def test_resolver_accepts_the_spaced_lowercase_form(db_session):
    patient = await _seed_patient(db_session)
    spaced = f"{patient.ramq_number[:4].lower()} {patient.ramq_number[4:8]} {patient.ramq_number[8:]}"
    assert await PatientResolver(PatientRepository(db_session)).resolve(spaced) == patient.id


async def test_resolver_without_a_nam_returns_none(db_session):
    resolver = PatientResolver(PatientRepository(db_session))
    assert await resolver.resolve(None) is None
    assert await resolver.resolve("") is None


async def test_resolver_rejects_a_malformed_nam(db_session):
    patient = await _seed_patient(db_session)
    # One digit short of a real NAM: never matched by prefix or fuzzily.
    assert await PatientResolver(PatientRepository(db_session)).resolve(patient.ramq_number[:-1]) is None


async def test_resolver_returns_none_for_an_unknown_nam(db_session):
    assert await PatientResolver(PatientRepository(db_session)).resolve("ZZZZ99999999") is None


async def test_resolver_ignores_a_soft_deleted_patient(db_session):
    patient = await _seed_patient(db_session)
    patient.deleted_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    await db_session.flush()
    assert await PatientResolver(PatientRepository(db_session)).resolve(patient.ramq_number) is None


# --- Deduplicator ---


def _key(user_id, *, note_text="Note signée.", external_note_id=None):
    return DedupKey(
        user_id=user_id,
        source_system="omnimed",
        content_hash=content_hash(note_text),
        external_note_id=external_note_id,
    )


async def _seed_encounter(session, user_id, *, note_text="Note signée.", external_note_id=None, patient_id=None, author_ref=None):
    return await EncounterRepository(session).create(
        EncounterInput(
            user_id=user_id,
            patient_id=patient_id,
            source_system="omnimed",
            channel=Channel.EXTENSION,
            content_hash=content_hash(note_text),
            note_text=note_text,
            external_note_id=external_note_id,
            service_date=DAY,
            encounter_meta={"author_ref": author_ref} if author_ref else None,
        )
    )


async def test_dedup_first_delivery_is_new(db_session, physician_id):
    result = await Deduplicator(EncounterRepository(db_session)).check(_key(physician_id, external_note_id="N-1"))
    assert result.outcome == DedupOutcome.NEW
    assert result.existing is None


async def test_dedup_same_external_id_and_hash_is_a_duplicate(db_session, physician_id):
    existing = await _seed_encounter(db_session, physician_id, external_note_id="N-1")
    result = await Deduplicator(EncounterRepository(db_session)).check(_key(physician_id, external_note_id="N-1"))
    assert result.outcome == DedupOutcome.DUPLICATE
    assert result.existing.id == existing.id


async def test_dedup_same_external_id_new_hash_is_a_new_version(db_session, physician_id):
    existing = await _seed_encounter(db_session, physician_id, external_note_id="N-1")
    result = await Deduplicator(EncounterRepository(db_session)).check(
        _key(physician_id, external_note_id="N-1", note_text="Note signée. Addendum : rappel en 2 sem.")
    )
    assert result.outcome == DedupOutcome.NEW_VERSION
    assert result.existing.id == existing.id


async def test_dedup_is_scoped_to_the_physician(db_session, physician_id):
    other = next(_physician_ids)
    await ensure_user_row(physician(other))
    await _seed_encounter(db_session, other, external_note_id="N-1")
    deduplicator = Deduplicator(EncounterRepository(db_session))
    assert (await deduplicator.check(_key(physician_id, external_note_id="N-1"))).outcome == DedupOutcome.NEW
    assert (await deduplicator.check(_key(physician_id))).outcome == DedupOutcome.NEW


async def test_dedup_without_external_id_same_text_is_a_duplicate(db_session, physician_id):
    # From any source: the extension's capture, pasted again by hand.
    existing = await _seed_encounter(db_session, physician_id, external_note_id="N-1")
    result = await Deduplicator(EncounterRepository(db_session)).check(_key(physician_id))
    assert result.outcome == DedupOutcome.DUPLICATE
    assert result.existing.id == existing.id


async def test_dedup_never_merges_different_texts_without_external_id(db_session, physician_id):
    # Same patient, day and author: often a second visit the same day, so never a duplicate.
    patient = await _seed_patient(db_session)
    await _seed_encounter(db_session, physician_id, patient_id=patient.id, author_ref="dr-42")
    result = await Deduplicator(EncounterRepository(db_session)).check(
        _key(physician_id, note_text="Revu en après-midi : fièvre persistante.")
    )
    assert result.outcome == DedupOutcome.NEW
