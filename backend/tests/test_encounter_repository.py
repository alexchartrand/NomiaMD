"""Exercises EncounterRepository and the derived encounter status (app/intake/status.py)
directly against the test DB — no HTTP. /extract's own encounter is covered by
tests/test_extraction.py."""

import itertools
import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.intake import Channel, EncounterStatus, content_hash, status_of
from app.postgresdb import (
    ClaimCodeInput,
    ClaimContextInput,
    ClaimInput,
    ClaimRepository,
    DuplicateEncounterError,
    Encounter,
    EncounterInput,
    EncounterRepository,
    ExtractionRepository,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunResult,
    ExtractionStageInput,
    Gender,
    PatientRepository,
)
from tests.db_helpers import ensure_user_row, physician

_physician_ids = itertools.count(3000)
# "ENCR" prefix, distinct from every other test file's — the test DB is shared across the
# whole session (see conftest.py) and patients are globally unique by NAM.
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
        ramq_number=f"ENCR{next(_ramq_numbers):08d}",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )


def _input(user_id, *, patient_id=None, note_text="Note signée.", external_note_id=None, service_date=DAY):
    return EncounterInput(
        user_id=user_id,
        patient_id=patient_id,
        source_system="omnimed",
        channel=Channel.EXTENSION,
        content_hash=content_hash(note_text),
        note_text=note_text,
        external_note_id=external_note_id,
        service_date=service_date,
    )


async def _seed_run(session, user_id, encounter):
    return await ExtractionRepository(session).create_run(
        ExtractionRunInput(
            user_id=user_id,
            encounter_id=encounter.id,
            patient_id=encounter.patient_id,
            stages=[ExtractionStageInput(task="billing_codes", model="mistral-small-latest", result={"codes": []})],
        )
    )


async def _seed_claim(session, user_id, encounter, run):
    return await ClaimRepository(session).create(
        ClaimInput(
            physician_id=user_id,
            patient_id=encounter.patient_id,
            service_date=DAY,
            source_system=encounter.source_system,
            source_note_hash=encounter.content_hash,
            external_note_id=encounter.external_note_id,
            extraction_run_id=run.id,
            context=ClaimContextInput(
                is_registered=None, is_vulnerable=None, patient_age_years=None, panel_size=None
            ),
            codes=[
                ClaimCodeInput(
                    code="TEST-BP-MGMT",
                    description="Prise en charge d'une hypertension",
                    confidence="high",
                    explanation="hypertension artérielle depuis 10 ans",
                    fee_amount=Decimal("33.15"),
                    fee_unit="dollars",
                    fee_units=None,
                    fee_role=None,
                    fee_context=None,
                    fee_lieux=None,
                    majoration=None,
                    manual_rev=None,
                )
            ],
        )
    )


async def _status(repo, user_id, encounter) -> EncounterStatus:
    [activity] = [a for a in await repo.list_for_day(user_id, DAY) if a.encounter.id == encounter.id]
    return status_of(activity)


def test_channel_enum_matches_the_check_constraint():
    [check] = [c for c in Encounter.__table__.constraints if c.name == "ck_encounters_channel"]
    allowed = set(re.findall(r"'([a-z_]+)'", str(check.sqltext)))
    assert allowed == {c.value for c in Channel}


async def test_create_then_get_for_user_is_scoped_to_its_owner(db_session, physician_id):
    other_id = physician_id + 100
    await ensure_user_row(physician(other_id))
    repo = EncounterRepository(db_session)

    encounter = await repo.create(_input(physician_id, external_note_id="note-1"))

    assert encounter.id is not None
    assert encounter.content_hash == content_hash("Note signée.")
    assert (await repo.get_for_user(encounter.id, physician_id)).id == encounter.id
    assert await repo.get_for_user(encounter.id, other_id) is None
    assert await repo.get_for_user(999_999, physician_id) is None


async def test_unique_index_accepts_a_new_version_but_rejects_a_duplicate(db_session, physician_id):
    repo = EncounterRepository(db_session)
    await repo.create(_input(physician_id, external_note_id="note-1", note_text="v1"))
    # Same external note, changed text: a new version, accepted.
    await repo.create(_input(physician_id, external_note_id="note-1", note_text="v2"))

    with pytest.raises(DuplicateEncounterError):
        await repo.create(_input(physician_id, external_note_id="note-1", note_text="v1"))


async def test_pasted_notes_without_an_external_id_are_never_deduplicated(db_session, physician_id):
    repo = EncounterRepository(db_session)
    first = await repo.create(_input(physician_id, note_text="même texte"))
    second = await repo.create(_input(physician_id, note_text="même texte"))

    assert first.id != second.id


async def test_list_for_day_is_the_owners_encounters_of_that_day_in_arrival_order(db_session, physician_id):
    other_id = physician_id + 100
    await ensure_user_row(physician(other_id))
    repo = EncounterRepository(db_session)
    first = await repo.create(_input(physician_id, note_text="a"))
    await repo.create(_input(physician_id, note_text="b", service_date=date(2026, 3, 5)))
    await repo.create(_input(physician_id, note_text="c", service_date=None))
    await repo.create(_input(other_id, note_text="d"))
    second = await repo.create(_input(physician_id, note_text="e"))

    listed = await repo.list_for_day(physician_id, DAY)

    assert [a.encounter.id for a in listed] == [first.id, second.id]


async def test_find_by_external_finds_an_exact_version_or_the_current_one(db_session, physician_id):
    repo = EncounterRepository(db_session)
    v1 = await repo.create(_input(physician_id, external_note_id="note-1", note_text="v1"))
    v2 = await repo.create(_input(physician_id, external_note_id="note-1", note_text="v2"))
    await repo.mark_superseded(v1, v2)

    assert (await repo.find_by_external(physician_id, "omnimed", "note-1", content_hash("v1"))).id == v1.id
    assert (await repo.find_by_external(physician_id, "omnimed", "note-1")).id == v2.id
    assert await repo.find_by_external(physician_id, "omnimed", "note-1", content_hash("v3")) is None
    assert await repo.find_by_external(physician_id, "telus", "note-1") is None


async def test_status_recu_then_pret_then_revu(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = EncounterRepository(db_session)
    encounter = await repo.create(_input(physician_id, patient_id=patient.id))
    assert await _status(repo, physician_id, encounter) == EncounterStatus.RECU

    run = await _seed_run(db_session, physician_id, encounter)
    assert await _status(repo, physician_id, encounter) == EncounterStatus.PRET

    created = await _seed_claim(db_session, physician_id, encounter, run)
    assert await _status(repo, physician_id, encounter) == EncounterStatus.REVU

    # Voiding the claim sends it back to review.
    await ClaimRepository(db_session).void(created.claim)
    assert await _status(repo, physician_id, encounter) == EncounterStatus.PRET


async def test_status_a_associer_without_a_patient_then_recu_once_set(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = EncounterRepository(db_session)
    encounter = await repo.create(_input(physician_id))
    assert await _status(repo, physician_id, encounter) == EncounterStatus.A_ASSOCIER

    await repo.set_patient(encounter, patient.id)
    assert await _status(repo, physician_id, encounter) == EncounterStatus.RECU


async def test_status_echec_until_a_run_succeeds(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = EncounterRepository(db_session)
    encounter = await repo.create(_input(physician_id, patient_id=patient.id))

    await repo.record_extraction_error(encounter, "TimeoutError: LLM")
    assert await _status(repo, physician_id, encounter) == EncounterStatus.ECHEC

    await _seed_run(db_session, physician_id, encounter)
    assert await _status(repo, physician_id, encounter) == EncounterStatus.PRET


async def test_status_modifie_wins_over_everything_else(db_session, physician_id):
    patient = await _seed_patient(db_session)
    repo = EncounterRepository(db_session)
    v1 = await repo.create(_input(physician_id, patient_id=patient.id, external_note_id="n", note_text="v1"))
    run = await _seed_run(db_session, physician_id, v1)
    await _seed_claim(db_session, physician_id, v1, run)
    v2 = await repo.create(_input(physician_id, external_note_id="n", note_text="v2"))

    await repo.mark_superseded(v1, v2)

    assert await _status(repo, physician_id, v1) == EncounterStatus.MODIFIE
    assert await _status(repo, physician_id, v2) == EncounterStatus.A_ASSOCIER


async def test_deleting_an_encounter_cascades_to_its_runs_and_keeps_the_claim(db_session, physician_id):
    patient = await _seed_patient(db_session)
    encounter = await EncounterRepository(db_session).create(
        _input(physician_id, patient_id=patient.id, external_note_id="note-1")
    )
    run = await _seed_run(db_session, physician_id, encounter)
    created = await _seed_claim(db_session, physician_id, encounter, run)

    await db_session.execute(delete(Encounter).where(Encounter.id == encounter.id))
    # The DB applied CASCADE / SET NULL, not the ORM — reload instead of reading cached rows.
    db_session.expunge_all()

    assert await db_session.get(ExtractionRun, run.id) is None
    results = await db_session.scalar(
        select(func.count()).select_from(ExtractionRunResult).where(ExtractionRunResult.run_id == run.id)
    )
    assert results == 0
    [detail] = await ClaimRepository(db_session).list_by_ids(physician_id, [created.claim.id])
    assert detail.claim.extraction_run_id is None
    assert detail.claim.source_system == "omnimed"
    assert detail.claim.source_note_hash == content_hash("Note signée.")
    assert detail.claim.external_note_id == "note-1"
    assert [c.code for c in detail.codes] == ["TEST-BP-MGMT"]
