"""The retention job (app/retention/): when a note's text is due, what scrubbing removes and
keeps. Dated around 1999 — the test DB is shared across the session (see conftest.py), and no
other test's rows are that old, so they're never due here."""

import itertools
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.clock import CLINIC_ZONE
from app.intake import Channel, content_hash
from app.postgresdb import (
    Claim,
    ClaimCodeInput,
    ClaimContextInput,
    ClaimInput,
    ClaimRepository,
    Encounter,
    EncounterInput,
    EncounterRepository,
    ExtractionRepository,
    ExtractionRunInput,
    ExtractionRunResult,
    ExtractionStageInput,
    Gender,
    PatientRepository,
)
from app.retention import NoteScrubber, RetentionPolicy
from tests.db_helpers import ensure_user_row, physician

_physician_ids = itertools.count(7000)
# "RETN" prefix: patients are globally unique by NAM across the shared test DB.
_ramq_numbers = itertools.count(1)

TODAY = date(2000, 1, 1)
NOW = datetime.combine(TODAY, time(12), CLINIC_ZONE).astimezone(timezone.utc)
POLICY = RetentionPolicy(note_unbilled_days=180, note_after_claim_days=365)
CUTOFFS = POLICY.scrub_cutoffs(TODAY, NOW)

_SELECTION = {
    "codes": [
        {
            "code": "00103",
            "description": "Visite",
            "confidence": "high",
            "explanation": "Visite de suivi",
            "supporting_quote": "toux depuis trois jours",
            "retained": True,
        }
    ],
    "notes": "Le patient mentionne aussi une douleur",
    "analysis": "Toux, examen pulmonaire normal",
}


@pytest.fixture
async def physician_id():
    user_id = next(_physician_ids)
    await ensure_user_row(physician(user_id))
    return user_id


@pytest.fixture
async def patient_id(db_session):
    patient = await PatientRepository(db_session).create(
        full_name="Rita Lemieux",
        ramq_number=f"RETN{next(_ramq_numbers):08d}",
        date_of_birth=date(1960, 5, 1),
        gender=Gender.FEMALE,
        is_vulnerable=False,
    )
    return patient.id


async def _encounter(session, user_id, patient_id, *, days_ago: int | None, note="Motif : toux depuis trois jours."):
    return await EncounterRepository(session).create(
        EncounterInput(
            user_id=user_id,
            patient_id=patient_id,
            source_system="omnimed",
            channel=Channel.EXTENSION,
            content_hash=content_hash(note),
            note_text=note,
            service_date=TODAY - timedelta(days=days_ago) if days_ago is not None else None,
        )
    )


async def _run(session, user_id, encounter):
    return await ExtractionRepository(session).create_run(
        ExtractionRunInput(
            user_id=user_id,
            encounter_id=encounter.id,
            patient_id=encounter.patient_id,
            stages=[
                ExtractionStageInput(task="consultation_summary", model="m", result={"chief_complaint": "toux"}),
                ExtractionStageInput(task="billing_codes", model="m", result=_SELECTION),
            ],
        )
    )


async def _claim(session, user_id, encounter, run, *, changed_days_ago: int):
    claim = await ClaimRepository(session).create(
        ClaimInput(
            physician_id=user_id,
            patient_id=encounter.patient_id,
            service_date=encounter.service_date,
            source_system=encounter.source_system,
            source_note_hash=encounter.content_hash,
            external_note_id=None,
            extraction_run_id=run.id,
            context=ClaimContextInput(is_registered=None, is_vulnerable=None, patient_age_years=None, panel_size=None),
            codes=[
                ClaimCodeInput(
                    code="00103",
                    description="Visite",
                    confidence="high",
                    explanation="Visite de suivi",
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
    await session.execute(
        update(Claim).where(Claim.id == claim.claim.id).values(updated_at=NOW - timedelta(days=changed_days_ago))
    )
    return claim.claim


async def _due_ids(session) -> set[int]:
    return {e.id for e in await EncounterRepository(session).list_due_for_scrub(CUTOFFS)}


async def test_an_unbilled_note_is_kept_180_days_after_its_visit(db_session, physician_id, patient_id):
    kept = await _encounter(db_session, physician_id, patient_id, days_ago=180)
    due = await _encounter(db_session, physician_id, patient_id, days_ago=181, note="Autre note.")

    ids = await _due_ids(db_session)
    assert due.id in ids
    assert kept.id not in ids


async def test_an_undated_note_counts_from_the_day_it_was_received(db_session, physician_id, patient_id):
    old = await _encounter(db_session, physician_id, patient_id, days_ago=None)
    received = datetime.combine(TODAY - timedelta(days=181), time(9), CLINIC_ZONE)
    await db_session.execute(update(Encounter).where(Encounter.id == old.id).values(created_at=received))

    assert old.id in await _due_ids(db_session)


async def test_a_claim_changed_within_a_year_keeps_the_note(db_session, physician_id, patient_id):
    encounter = await _encounter(db_session, physician_id, patient_id, days_ago=400)
    claim = await _claim(db_session, physician_id, encounter, await _run(db_session, physician_id, encounter), changed_days_ago=200)
    assert encounter.id not in await _due_ids(db_session)

    # A year after its last change (billing, a re-bill after a refusal), the note goes.
    await db_session.execute(update(Claim).where(Claim.id == claim.id).values(updated_at=NOW - timedelta(days=366)))
    assert encounter.id in await _due_ids(db_session)


async def test_a_voided_claim_holds_nothing(db_session, physician_id, patient_id):
    encounter = await _encounter(db_session, physician_id, patient_id, days_ago=400)
    claim = await _claim(db_session, physician_id, encounter, await _run(db_session, physician_id, encounter), changed_days_ago=10)
    await db_session.execute(update(Claim).where(Claim.id == claim.id).values(voided_at=NOW))

    assert encounter.id in await _due_ids(db_session)


async def test_a_restored_note_is_kept_180_days_again(db_session, physician_id, patient_id):
    encounter = await _encounter(db_session, physician_id, patient_id, days_ago=400)
    repo = EncounterRepository(db_session)
    await repo.scrub_note(encounter, NOW - timedelta(days=30))
    await repo.restore_note(encounter, "Motif : toux depuis trois jours.", NOW - timedelta(days=10))
    assert encounter.id not in await _due_ids(db_session)

    await repo.restore_note(encounter, "Motif : toux depuis trois jours.", NOW - timedelta(days=181))
    assert encounter.id in await _due_ids(db_session)


async def test_scrubbing_removes_the_clinical_text_and_keeps_the_billing(db_session, physician_id, patient_id):
    encounter = await _encounter(db_session, physician_id, patient_id, days_ago=500)
    run = await _run(db_session, physician_id, encounter)
    claim = await _claim(db_session, physician_id, encounter, run, changed_days_ago=400)
    await EncounterRepository(db_session).record_extraction_error(encounter, "échec sur « toux »")
    note_hash = encounter.content_hash

    await NoteScrubber(db_session).scrub_due(CUTOFFS, NOW)

    await db_session.refresh(encounter)
    assert encounter.note_text is None
    assert encounter.extraction_error is None
    assert encounter.note_scrubbed_at is not None
    assert encounter.content_hash == note_hash
    results = {
        r.task: r.result_json
        for r in await db_session.scalars(select(ExtractionRunResult).where(ExtractionRunResult.run_id == run.id))
    }
    assert set(results) == {"billing_codes"}
    [code] = results["billing_codes"]["codes"]
    assert (code["code"], code["retained"], code["explanation"], code["supporting_quote"]) == (
        "00103",
        True,
        "Visite de suivi",
        "",
    )
    assert results["billing_codes"]["analysis"] is None
    assert results["billing_codes"]["notes"] is None
    await db_session.refresh(claim)
    assert claim.extraction_run_id == run.id
    assert claim.source_note_hash == note_hash
    assert claim.voided_at is None


async def test_scrubbing_leaves_notes_still_in_retention_alone(db_session, physician_id, patient_id):
    encounter = await _encounter(db_session, physician_id, patient_id, days_ago=30)
    run = await _run(db_session, physician_id, encounter)

    await NoteScrubber(db_session).scrub_due(CUTOFFS, NOW)

    await db_session.refresh(encounter)
    assert encounter.note_text is not None
    tasks = set(await db_session.scalars(select(ExtractionRunResult.task).where(ExtractionRunResult.run_id == run.id)))
    assert tasks == {"consultation_summary", "billing_codes"}
