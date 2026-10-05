"""The dashboard's pure pieces — the RAMQ deadline arithmetic, the to-do counts, the
deadline list and the weekly buckets — over hand-built inbox rows. No DB, no HTTP."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.dashboard.activity import WeeklyActivity, clinic_day_of
from app.dashboard.deadline import BillingDeadline
from app.dashboard.deadlines import DeadlineWatch
from app.dashboard.tasks import TaskCounter
from app.encounters.models import EncounterRowOut, MaskedPatientOut
from app.intake import EncounterStatus

TODAY = date(2026, 10, 7)  # a Wednesday


def _row(
    id: int,
    status: EncounterStatus = EncounterStatus.PRET,
    *,
    service_date: date | None = TODAY,
    received_at: datetime = datetime(2026, 10, 7, 14, tzinfo=timezone.utc),
    all_clean: bool = False,
    duplicates: list[int] | None = None,
) -> EncounterRowOut:
    return EncounterRowOut(
        id=id,
        status=status,
        patient=MaskedPatientOut(id=1, display_name="Roch D.", nam=None),
        source_system="omnimed",
        channel="extension",
        batch_label=None,
        service_date=service_date,
        received_at=received_at,
        code_count=None,
        extraction_run_id=None,
        possible_duplicate_ids=duplicates or [],
        all_clean=all_clean,
        deletable=True,
    )


@pytest.mark.parametrize(
    ("service_date", "days_left", "at_risk"),
    [
        (date(2026, 7, 9), 0, True),  # 90 days ago: the last day
        (date(2026, 7, 4), -5, True),
        (date(2026, 7, 24), 15, True),
        (date(2026, 7, 25), 16, False),
        (TODAY, 90, False),
    ],
)
def test_billing_deadline(service_date, days_left, at_risk):
    deadline = BillingDeadline()
    assert deadline.days_left(service_date, TODAY) == days_left
    assert deadline.is_at_risk(days_left) is at_risk


def test_task_counter():
    rows = [
        _row(1, EncounterStatus.PRET, all_clean=True),
        _row(2, EncounterStatus.PRET, duplicates=[3]),
        _row(3, EncounterStatus.REVU, duplicates=[2]),
        _row(4, EncounterStatus.A_ASSOCIER),
        _row(5, EncounterStatus.ECHEC),
        _row(6, EncounterStatus.RECU),
        _row(7, EncounterStatus.MODIFIE),
    ]
    counts = TaskCounter.count(rows)
    assert counts.model_dump() == {
        "to_do": 5,
        "to_review": 2,
        "approvable": 1,
        "to_associate": 1,
        "failed": 1,
        "extracting": 1,
        "possible_duplicates": 2,
    }


def test_deadline_watch_skips_reviewed_outdated_and_undated_encounters():
    old = date(2026, 7, 10)  # 1 day left
    rows = [
        _row(1, EncounterStatus.PRET, service_date=old),
        _row(2, EncounterStatus.REVU, service_date=old),
        _row(3, EncounterStatus.MODIFIE, service_date=old),
        _row(4, EncounterStatus.A_ASSOCIER, service_date=None),
    ]
    draft = SimpleNamespace(
        claim=SimpleNamespace(id=9, service_date=date(2026, 7, 8)), patient_full_name="Marie Tremblay", codes=[]
    )

    items = DeadlineWatch(BillingDeadline()).items(rows, [draft], TODAY)

    assert [(i.kind, i.id, i.days_left, i.patient_display) for i in items] == [
        ("claim", 9, -1, "Marie T."),
        ("encounter", 1, 1, "Roch D."),
    ]


def test_an_undated_encounter_counts_on_the_clinic_day_it_was_received():
    # 02:00 UTC on Tuesday is still Monday evening in Montréal.
    row = _row(1, service_date=None, received_at=datetime(2026, 10, 6, 2, tzinfo=timezone.utc))
    assert clinic_day_of(row) == date(2026, 10, 5)


def test_weekly_activity_buckets_by_monday_including_empty_weeks():
    rows = [
        _row(1, service_date=date(2026, 10, 5)),  # this week's Monday
        _row(2, EncounterStatus.REVU, service_date=date(2026, 10, 11)),  # this week's Sunday
        _row(3, service_date=date(2026, 10, 4)),  # last week's Sunday
        _row(4, service_date=date(2026, 8, 1)),  # before the window
    ]

    buckets = WeeklyActivity(weeks=3).buckets(rows, TODAY)

    assert [(b.week_start, b.received, b.reviewed) for b in buckets] == [
        (date(2026, 9, 21), 0, 0),
        (date(2026, 9, 28), 1, 0),
        (date(2026, 10, 5), 2, 1),
    ]

