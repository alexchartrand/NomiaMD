"""Exercises PatientSuggestionService (app/patients/suggestion.py) against a real (test) DB
via PatientRepository — no HTTP, no mocked model."""

import itertools
from datetime import date

import pytest

from app.patients import ExtractedIdentity, PatientSuggestionService
from app.postgresdb import Gender, PatientRepository, init_db

ON_DATE = date(2026, 2, 10)

# The test DB is shared (session-scoped file, not reset per test — see conftest.py), so each
# test gets its own physician_id to keep its roster isolated from every other test's.
_physician_ids = itertools.count(1000)


@pytest.fixture(autouse=True)
async def _init_db():
    # These tests hit PatientRepository directly rather than going through TestClient(app)
    # (whose lifespan calls init_db()), so the schema needs creating explicitly.
    await init_db()


@pytest.fixture
def physician_id():
    return next(_physician_ids)


async def _seed_patient(
    *,
    physician_id,
    full_name="Roch Desjardins",
    ramq_number="DESR81021001",
    date_of_birth=date(1981, 2, 10),
    gender=Gender.MALE,
):
    return await PatientRepository().create(
        physician_id=physician_id,
        full_name=full_name,
        ramq_number=ramq_number,
        date_of_birth=date_of_birth,
        gender=gender,
        is_registered_with_physician=True,
        is_vulnerable=False,
    )


@pytest.fixture
def service():
    return PatientSuggestionService()


async def test_exact_nam_hit_identifies_the_patient(service, physician_id):
    patient = await _seed_patient(physician_id=physician_id)
    extracted = ExtractedIdentity(
        ramq_number="DESR81021001", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id == patient.id


async def test_differently_spaced_or_lowercase_roster_nam_still_matches(service, physician_id):
    patient = await _seed_patient(physician_id=physician_id, ramq_number="desr 8102-1001")
    extracted = ExtractedIdentity(
        ramq_number="DESR 8102 1001", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id == patient.id


async def test_nam_matching_nobody_has_no_match_but_extracted_is_populated(service, physician_id):
    extracted = ExtractedIdentity(
        ramq_number="PAQN81031501", name_as_stated="Paquette, Nathalie", age_years=45, age_months=None, sex="F"
    )

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id is None
    assert suggestion.extracted.name_as_stated == "Paquette, Nathalie"
    assert suggestion.prefill.suggested_full_name == "Nathalie Paquette"


async def test_identical_name_with_different_nam_is_not_a_match(service, physician_id):
    await _seed_patient(physician_id=physician_id, full_name="Roch Desjardins", ramq_number="DESR81021001")
    extracted = ExtractedIdentity(
        ramq_number="DESR99999999", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id is None


async def test_roster_patient_with_null_ramq_number_is_never_matched(service, physician_id):
    await PatientRepository().create(
        physician_id=physician_id,
        full_name="Sans NAM",
        ramq_number=None,
        date_of_birth=date(1990, 1, 1),
        gender=None,
        is_registered_with_physician=True,
        is_vulnerable=False,
    )
    extracted = ExtractedIdentity(ramq_number=None, name_as_stated=None, age_years=None, age_months=None, sex=None)

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id is None


async def test_duplicate_nam_across_roster_rows_is_no_match_not_a_coin_flip(service, physician_id, caplog):
    # ix_patients_physician_ramq_number_active (models.py) blocks two roster rows sharing
    # the exact same literal NAM string, but _match compares via nam.normalize()
    # (case/spacing-insensitive) — two different literal strings that normalize to the
    # same NAM still slip past that constraint, so this state is still reachable through
    # the ordinary PatientRepository.create path.
    await _seed_patient(physician_id=physician_id, full_name="Roch Desjardins", ramq_number="DESR81021001")
    await _seed_patient(
        physician_id=physician_id, full_name="Roch Desjardins Deux", ramq_number="desr 8102-1001"
    )
    extracted = ExtractedIdentity(
        ramq_number="DESR81021001", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )

    with caplog.at_level("WARNING"):
        suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id is None
    assert any("share NAM" in record.message for record in caplog.records)


async def test_malformed_or_absent_nam_no_lookup_no_match(service, physician_id):
    await _seed_patient(physician_id=physician_id)
    extracted = ExtractedIdentity(
        ramq_number="not-a-nam", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id is None

    extracted_absent = ExtractedIdentity(
        ramq_number=None, name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )
    suggestion_absent = await service.suggest(extracted_absent, physician_id=physician_id, on_date=ON_DATE)
    assert suggestion_absent.matched_patient_id is None


async def test_soft_deleted_patient_is_never_matched(service, physician_id):
    patient = await _seed_patient(physician_id=physician_id)
    assert await PatientRepository().delete_for_physician(patient.id, physician_id) is True

    extracted = ExtractedIdentity(
        ramq_number="DESR81021001", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )
    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.matched_patient_id is None


async def test_prefill_comma_flip_and_nam_decoded_dob_not_estimated(service, physician_id):
    extracted = ExtractedIdentity(
        ramq_number="DESR81021001", name_as_stated="Desjardins, Roch", age_years=45, age_months=None, sex="H"
    )

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.prefill.suggested_full_name == "Roch Desjardins"
    assert suggestion.prefill.suggested_date_of_birth == date(1981, 2, 10)
    assert suggestion.prefill.date_of_birth_is_estimated is False
    assert suggestion.prefill.suggested_gender == Gender.MALE


async def test_prefill_age_derived_dob_is_flagged_estimated_without_nam(service, physician_id):
    extracted = ExtractedIdentity(ramq_number=None, name_as_stated="Simard, Yannick", age_years=38, age_months=None, sex="H")

    suggestion = await service.suggest(extracted, physician_id=physician_id, on_date=ON_DATE)

    assert suggestion.prefill.date_of_birth_is_estimated is True
    assert suggestion.prefill.suggested_date_of_birth == date(1988, 1, 1)
    assert suggestion.prefill.suggested_gender == Gender.MALE
