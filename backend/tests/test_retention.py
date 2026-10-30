"""The retention job (app/retention/): when a note's text is due, what scrubbing removes and
keeps. Dated around 1999 — the test DB is shared across the session (see conftest.py), and no
other test's rows are that old, so they're never due here."""

import itertools
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select, update

from app.admin.pricing import PriceTable
from app.admin.usage import UsageGrouping, UsageReport
from app.clock import CLINIC_ZONE, clinic_day_bounds, clinic_day_of
from app.intake import Channel, content_hash
from app.llm.usage import LLMCallRecord
from app.postgresdb import (
    AuditEvent,
    AuditEventInput,
    AuditEventRepository,
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
    LLMCallOwner,
    LLMCallRepository,
    LLMUsageDayRepository,
    PatientRepository,
    UserRepository,
    session_scope,
)
from app.retention import LLMUsageRollup, NoteScrubber, RetentionJob, RetentionPolicy
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


class _Clock:
    def today(self) -> date:
        return TODAY

    def now(self) -> datetime:
        return NOW


async def _audit_event(days_ago: int) -> int:
    async with session_scope() as session:
        event = await AuditEventRepository(session).add(AuditEventInput(action="login_succeeded", ip="10.0.0.1"))
        await session.execute(
            update(AuditEvent).where(AuditEvent.id == event.id).values(created_at=NOW - timedelta(days=days_ago))
        )
        return event.id


async def _audit_ids(ids: list[int]) -> set[int]:
    async with session_scope() as session:
        return set(await session.scalars(select(AuditEvent.id).where(AuditEvent.id.in_(ids))))


async def test_the_job_deletes_audit_events_after_a_year():
    old, recent = await _audit_event(366), await _audit_event(364)

    report = await RetentionJob(RetentionPolicy(audit_days=365), _Clock()).run()

    assert report.audit_events_deleted is not None and report.audit_events_deleted >= 1
    assert await _audit_ids([old, recent]) == {recent}


async def test_a_dry_run_counts_without_deleting():
    old = await _audit_event(400)

    report = await RetentionJob(RetentionPolicy(audit_days=365), _Clock()).run(dry_run=True)

    assert report.audit_events_deleted is not None and report.audit_events_deleted >= 1
    assert await _audit_ids([old]) == {old}


async def test_a_failing_step_is_logged_and_the_others_still_run(caplog):
    old = await _audit_event(400)

    with patch.object(NoteScrubber, "scrub_due", side_effect=RuntimeError("boom")):
        report = await RetentionJob(RetentionPolicy(audit_days=365), _Clock()).run()

    assert report.notes_scrubbed is None
    assert "retention step notes_scrubbed failed" in caplog.text
    assert await _audit_ids([old]) == set()


# --- llm_calls rollup ----------------------------------------------------------------

ROLLUP_FIRST, ROLLUP_LAST = date(1999, 9, 1), date(1999, 9, 30)


def _call(day: date, *, model="mistral-small-latest", purpose="billing_codes", tokens=(1000, 200), error=None):
    return LLMCallRecord(
        kind="chat",
        provider="mistral",
        model=model,
        purpose=purpose,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        latency_ms=850.0,
        # 23:30 in Montréal: already the next day in UTC, so the clinic day is what's folded.
        started_at=datetime.combine(day, time(23, 30), CLINIC_ZONE).astimezone(timezone.utc),
        error=error,
    )


async def _seed_calls(session, user_id, patient_id):
    encounter = await _encounter(session, user_id, patient_id, days_ago=120)
    run = await _run(session, user_id, encounter)
    calls = LLMCallRepository(session)
    owner = LLMCallOwner(user_id=user_id, encounter_id=encounter.id, run_id=run.id)
    await calls.add_many(
        [_call(date(1999, 9, 3), purpose="consultation_summary"), _call(date(1999, 9, 3))], owner
    )
    await calls.add_many([_call(date(1999, 9, 3), purpose="ramq_chatbot", error="Timeout")], LLMCallOwner(user_id))
    await calls.add_many(
        [_call(date(1999, 9, 20), model="unpriced-model", purpose="ramq_chatbot", tokens=(50, 5))],
        LLMCallOwner(user_id),
    )
    return run


def _report(session) -> UsageReport:
    return UsageReport(
        LLMCallRepository(session), LLMUsageDayRepository(session), UserRepository(session), PriceTable.from_settings()
    )


def _bucket_numbers(bucket):
    return (bucket.key, bucket.calls, bucket.input_tokens, bucket.output_tokens, bucket.cost, bucket.unpriced_calls, bucket.errors)


async def test_the_rollup_folds_whole_clinic_days_and_deletes_the_raw_calls(db_session, physician_id, patient_id):
    await _seed_calls(db_session, physician_id, patient_id)
    rollup = LLMUsageRollup(db_session)
    before = clinic_day_bounds(date(1999, 10, 1))[0]

    assert await rollup.roll_up(before) == 4

    rows = {
        (r.day, r.purpose, r.in_extraction): (r.calls, r.input_tokens, r.output_tokens, r.errors)
        for r in await LLMUsageDayRepository(db_session).list_between(ROLLUP_FIRST, ROLLUP_LAST)
        if r.user_id == physician_id
    }
    assert rows == {
        (date(1999, 9, 3), "consultation_summary", True): (1, 1000, 200, 0),
        (date(1999, 9, 3), "billing_codes", True): (1, 1000, 200, 0),
        (date(1999, 9, 3), "ramq_chatbot", False): (1, 1000, 200, 1),
        (date(1999, 9, 20), "ramq_chatbot", False): (1, 50, 5, 0),
    }
    [extractions] = [
        r for r in await LLMUsageDayRepository(db_session).list_extractions_between(ROLLUP_FIRST, ROLLUP_LAST)
        if r.user_id == physician_id
    ]
    assert (extractions.day, extractions.extractions) == (date(1999, 9, 3), 1)
    assert await LLMCallRepository(db_session).count_before(before) == 0
    # Nothing raw is left before the cut-off: a rerun folds nothing twice.
    assert await rollup.roll_up(before) == 0


async def test_the_rollup_leaves_days_still_kept_raw(db_session, physician_id, patient_id):
    await _seed_calls(db_session, physician_id, patient_id)

    await LLMUsageRollup(db_session).roll_up(clinic_day_bounds(date(1999, 9, 20))[0])

    remaining = await LLMCallRepository(db_session).list_between(*_range_instants())
    assert [clinic_day_of(c.started_at) for c in remaining if c.user_id == physician_id] == [date(1999, 9, 20)]


def _range_instants():
    return clinic_day_bounds(ROLLUP_FIRST)[0], clinic_day_bounds(ROLLUP_LAST)[1]


@pytest.mark.parametrize("grouping", list(UsageGrouping))
async def test_the_usage_report_reads_the_same_before_and_after_the_rollup(db_session, physician_id, patient_id, grouping):
    await _seed_calls(db_session, physician_id, patient_id)
    raw = await _report(db_session).build(ROLLUP_FIRST, ROLLUP_LAST, grouping)

    # Half the month rolled up, half still raw: the report adds both.
    await LLMUsageRollup(db_session).roll_up(clinic_day_bounds(date(1999, 9, 10))[0])
    mixed = await _report(db_session).build(ROLLUP_FIRST, ROLLUP_LAST, grouping)

    assert _bucket_numbers(mixed.totals) == _bucket_numbers(raw.totals)
    assert mixed.extractions == raw.extractions == 1
    assert mixed.cost_per_extraction == raw.cost_per_extraction is not None
    assert [_bucket_numbers(b) for b in mixed.by_day] == [_bucket_numbers(b) for b in raw.by_day]
    assert [_bucket_numbers(b) for b in mixed.breakdown] == [_bucket_numbers(b) for b in raw.breakdown]
    # The rolled-up 3rd has no latencies left; the raw 20th still does.
    assert mixed.by_day[2].median_latency_ms is None
    assert mixed.by_day[19].median_latency_ms == 850.0
