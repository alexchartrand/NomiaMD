from datetime import date

from app.extraction.encounter_date import DateOrder, parse_encounter_date


def test_none_and_blank_return_none():
    assert parse_encounter_date(None) is None
    assert parse_encounter_date("") is None
    assert parse_encounter_date("   ") is None


def test_iso_date():
    assert parse_encounter_date("2026-02-10") == date(2026, 2, 10)


def test_iso_datetime():
    assert parse_encounter_date("2026-02-10T09:15") == date(2026, 2, 10)


def test_french_date_with_accent():
    assert parse_encounter_date("10 février 2026") == date(2026, 2, 10)


def test_french_date_without_accent():
    assert parse_encounter_date("10 fevrier 2026") == date(2026, 2, 10)


def test_french_date_embedded_in_sentence():
    assert parse_encounter_date("Consultation du 9 juin 2026 en après-midi") == date(2026, 6, 9)


def test_slash_date():
    assert parse_encounter_date("10/02/2026") == date(2026, 2, 10)


def test_unrecognized_text_returns_none():
    assert parse_encounter_date("pas de date mentionnée") is None


def test_impossible_date_returns_none():
    assert parse_encounter_date("31 février 2026") is None


def test_slash_date_month_first_when_the_source_says_so():
    assert parse_encounter_date("02/10/2026", DateOrder.MDY) == date(2026, 2, 10)


def test_ambiguous_slash_date_follows_the_source_order():
    assert parse_encounter_date("03/04/2026", DateOrder.DMY) == date(2026, 4, 3)
    assert parse_encounter_date("03/04/2026", DateOrder.MDY) == date(2026, 3, 4)


def test_month_first_order_rejects_a_day_first_date():
    assert parse_encounter_date("25/12/2026", DateOrder.MDY) is None


def test_date_order_does_not_affect_unambiguous_formats():
    assert parse_encounter_date("2026-02-10", DateOrder.MDY) == date(2026, 2, 10)
    assert parse_encounter_date("10 février 2026", DateOrder.MDY) == date(2026, 2, 10)
