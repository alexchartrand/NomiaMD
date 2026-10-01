"""SameVisitMatcher — pure, over unsaved Encounter objects; no DB."""

from datetime import date

from app.intake import SameVisitMatcher
from app.postgresdb import Encounter

DAY = date(2026, 3, 4)
_ids = iter(range(1, 1000))


def _encounter(*, patient_id=10, service_date=DAY, user_id=1, author_ref="dr-42", time_start=None):
    meta = {k: v for k, v in {"author_ref": author_ref, "time_start": time_start}.items() if v is not None}
    return Encounter(
        id=next(_ids), user_id=user_id, patient_id=patient_id, service_date=service_date, encounter_meta=meta or None
    )


matcher = SameVisitMatcher()


def test_same_patient_day_and_author_may_be_the_same_visit():
    assert matcher.may_be_same_visit(_encounter(), _encounter())


def test_an_encounter_is_not_its_own_duplicate():
    encounter = _encounter()
    assert not matcher.may_be_same_visit(encounter, encounter)


def test_different_patient_day_or_physician_rules_it_out():
    assert not matcher.may_be_same_visit(_encounter(), _encounter(patient_id=11))
    assert not matcher.may_be_same_visit(_encounter(), _encounter(service_date=date(2026, 3, 5)))
    assert not matcher.may_be_same_visit(_encounter(), _encounter(user_id=2))


def test_an_unknown_patient_or_day_never_matches():
    assert not matcher.may_be_same_visit(_encounter(patient_id=None), _encounter(patient_id=None))
    assert not matcher.may_be_same_visit(_encounter(service_date=None), _encounter(service_date=None))


def test_a_different_author_rules_it_out_but_an_unknown_one_does_not():
    assert not matcher.may_be_same_visit(_encounter(), _encounter(author_ref="dr-7"))
    assert matcher.may_be_same_visit(_encounter(), _encounter(author_ref=None))


def test_start_times_far_apart_are_two_visits():
    assert not matcher.may_be_same_visit(_encounter(time_start="09:00:00"), _encounter(time_start="15:00:00"))


def test_start_times_within_tolerance_may_be_the_same_visit():
    assert matcher.may_be_same_visit(_encounter(time_start="09:00:00"), _encounter(time_start="09:20:00"))


def test_an_unknown_or_unreadable_time_does_not_rule_it_out():
    assert matcher.may_be_same_visit(_encounter(time_start="09:00:00"), _encounter())
    assert matcher.may_be_same_visit(_encounter(time_start="09:00:00"), _encounter(time_start="9h"))
