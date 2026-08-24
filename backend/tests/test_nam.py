"""Pure unit tests for the NAM value object (app/patients/nam.py) — no DB, no HTTP."""

from datetime import date

from app.patients.nam import decode, normalize
from app.postgresdb import Gender

ON_DATE = date(2026, 2, 10)


def test_normalize_accepts_spaced_and_hyphenated_forms():
    assert normalize("DESR 8102 1001") == "DESR81021001"
    assert normalize("desr-8102-1001") == "DESR81021001"


def test_normalize_rejects_malformed_input():
    assert normalize("#CLI-2026-01220") is None
    assert normalize("DESR810210") is None
    assert normalize("") is None
    assert normalize(None) is None


def test_decode_male():
    identity = decode("DESR81021001", on_date=ON_DATE)
    assert identity is not None
    assert identity.date_of_birth == date(1981, 2, 10)
    assert identity.gender == Gender.MALE


def test_decode_female_month_plus_fifty():
    identity = decode("NADS94552201", on_date=ON_DATE)
    assert identity is not None
    assert identity.date_of_birth == date(1994, 5, 22)
    assert identity.gender == Gender.FEMALE


def test_decode_invalid_month_returns_none():
    assert decode("TEST80000101", on_date=ON_DATE) is None  # month 00
    assert decode("TEST80300101", on_date=ON_DATE) is None  # month 30, between 13 and 50
    assert decode("TEST80990101", on_date=ON_DATE) is None  # month 99, above 62


def test_decode_impossible_day_returns_none():
    assert decode("TEST80023101", on_date=ON_DATE) is None  # Feb 31 in any century


def test_decode_future_year_falls_back_to_previous_century():
    # yy=30 -> 2030 is in the future relative to on_date, so only 1930 remains.
    identity = decode("TEST30011501", on_date=ON_DATE)
    assert identity is not None
    assert identity.date_of_birth == date(1930, 1, 15)


def test_decode_ambiguous_century_without_age_hint_returns_none():
    # yy=24 -> both 1924 (age 102, <=120) and 2024 (age 2) are plausible on their own.
    assert decode("TEST24011501", on_date=ON_DATE) is None


def test_decode_ambiguous_century_with_age_hint_resolves():
    identity = decode("TEST24011501", on_date=ON_DATE, age_hint=2)
    assert identity is not None
    assert identity.date_of_birth == date(2024, 1, 15)

    identity_old = decode("TEST24011501", on_date=ON_DATE, age_hint=102)
    assert identity_old is not None
    assert identity_old.date_of_birth == date(1924, 1, 15)
