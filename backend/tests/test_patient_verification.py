"""Exercises verify_patient_identity (app/patients/verification.py) — a pure comparison
between what a transcript stated and the patient chosen before extraction ran. No DB, no
HTTP: Patient is constructed directly, same convention as test_ramq_codes_context.py."""

from datetime import date

from app.patients.verification import ExtractedIdentity, verify_patient_identity
from app.postgresdb import Gender, Patient

ON_DATE = date(2026, 2, 10)


def _patient(**overrides) -> Patient:
    defaults = dict(
        id=1,
        full_name="Roch Desjardins",
        ramq_number="DESR81021001",
        date_of_birth=date(1981, 2, 10),
        gender=Gender.MALE,
        is_vulnerable=False,
    )
    return Patient(**{**defaults, **overrides})


def _extracted(**overrides) -> ExtractedIdentity:
    defaults = dict(ramq_number=None, name_as_stated=None, age_years=None, age_months=None, sex=None)
    return ExtractedIdentity(**{**defaults, **overrides})


def test_everything_agreeing_has_no_mismatches():
    verification = verify_patient_identity(
        _extracted(ramq_number="DESR81021001", name_as_stated="Desjardins, Roch", age_years=45),
        patient=_patient(),
        on_date=ON_DATE,
    )

    assert verification.nam_mismatch is False
    assert verification.name_mismatch is False
    assert verification.age_mismatch is False


def test_differently_spaced_or_lowercase_nam_still_agrees():
    verification = verify_patient_identity(
        _extracted(ramq_number="desr 8102-1001"), patient=_patient(), on_date=ON_DATE
    )

    assert verification.nam_mismatch is False


def test_different_nam_is_a_mismatch():
    verification = verify_patient_identity(
        _extracted(ramq_number="PAQN81031501"), patient=_patient(), on_date=ON_DATE
    )

    assert verification.nam_mismatch is True


def test_transcript_stating_a_nam_the_patient_has_none_of_is_a_mismatch():
    verification = verify_patient_identity(
        _extracted(ramq_number="DESR81021001"), patient=_patient(ramq_number=None), on_date=ON_DATE
    )

    assert verification.nam_mismatch is True


def test_no_nam_stated_is_not_a_mismatch():
    verification = verify_patient_identity(_extracted(), patient=_patient(), on_date=ON_DATE)

    assert verification.nam_mismatch is None


def test_name_mismatch_case_and_comma_insensitive():
    verification = verify_patient_identity(
        _extracted(name_as_stated="desjardins, roch"), patient=_patient(), on_date=ON_DATE
    )

    assert verification.name_mismatch is False


def test_different_name_is_a_mismatch():
    verification = verify_patient_identity(
        _extracted(name_as_stated="Paquette, Nathalie"), patient=_patient(), on_date=ON_DATE
    )

    assert verification.name_mismatch is True


def test_no_name_stated_is_not_a_mismatch():
    verification = verify_patient_identity(_extracted(), patient=_patient(), on_date=ON_DATE)

    assert verification.name_mismatch is None


def test_age_within_one_year_tolerance_is_not_a_mismatch():
    # Born 1981-02-10; on 2026-02-10 they are exactly 45.
    verification = verify_patient_identity(_extracted(age_years=44), patient=_patient(), on_date=ON_DATE)

    assert verification.age_mismatch is False


def test_age_beyond_tolerance_is_a_mismatch():
    verification = verify_patient_identity(_extracted(age_years=60), patient=_patient(), on_date=ON_DATE)

    assert verification.age_mismatch is True


def test_age_months_used_for_an_infant():
    verification = verify_patient_identity(
        _extracted(age_months=6), patient=_patient(date_of_birth=date(2025, 8, 10)), on_date=ON_DATE
    )

    assert verification.age_mismatch is False


def test_no_age_stated_is_not_a_mismatch():
    verification = verify_patient_identity(_extracted(), patient=_patient(), on_date=ON_DATE)

    assert verification.age_mismatch is None
