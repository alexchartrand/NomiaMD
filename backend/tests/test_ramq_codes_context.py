"""Unit tests for BillingContextBuilder (app/ramq_codes/context_builder.py), isolated from
the real ProfileService/PatientRepository via small fakes — same convention as
test_ramq_codes_task.py's _FakeRetriever. Constructs User/Patient (plain SQLAlchemy
declarative models) directly rather than through a DB session: attribute access alone
doesn't need a session, and these tests have nothing to do with persistence."""

from datetime import date

from app.auth.profile import PhysicianAccount
from app.postgresdb import Gender, Patient, PhysicianProfile, User, UserRole
from app.ramq_codes.context_builder import BillingContextBuilder

PATIENT_ID = 2


class _FakeProfileService:
    def __init__(self, profile: PhysicianProfile | None, earliest: PhysicianProfile | None = None):
        self._profile = profile
        self._earliest = earliest
        self.as_of_calls: list[tuple[User, date]] = []
        self.earliest_calls: list[User] = []

    async def as_of(self, user: User, on: date) -> PhysicianAccount:
        self.as_of_calls.append((user, on))
        return PhysicianAccount(user=user, profile=self._profile)

    async def earliest(self, user: User) -> PhysicianAccount:
        self.earliest_calls.append(user)
        return PhysicianAccount(user=user, profile=self._earliest)


class _FakePatientRepository:
    def __init__(self, patient: Patient | None):
        self._patient = patient

    async def get(self, patient_id: int) -> Patient | None:
        return self._patient


def _user(**overrides) -> User:
    defaults = dict(
        id=1, email="doc@example.test", hashed_password="x", full_name="Dr. Doe", role=UserRole.PHYSICIAN
    )
    return User(**{**defaults, **overrides})


def _profile(**overrides) -> PhysicianProfile:
    defaults = dict(
        id=1, user_id=1, effective_from=date(2026, 1, 1),
        physician_type="omnipraticien", number_of_patients=320, remuneration_type="mixte",
    )
    return PhysicianProfile(**{**defaults, **overrides})


def _patient(**overrides) -> Patient:
    defaults = dict(
        id=PATIENT_ID, full_name="Jean Tremblay", date_of_birth=date(1968, 3, 10),
        gender=Gender.MALE, is_vulnerable=False, family_doctor_practice_number=None,
    )
    return Patient(**{**defaults, **overrides})


async def test_no_profile_and_no_patient_yields_an_all_null_context():
    builder = BillingContextBuilder(_FakeProfileService(None), _FakePatientRepository(None))

    context = await builder.build(user=_user(), patient_id=999, encounter_date=date(2026, 6, 1))

    assert context.physician.number_of_patients is None
    assert context.patient.age_years is None
    assert context.patient.is_registered is None
    assert context.patient.is_vulnerable is None


async def test_profile_facts_carry_through_when_a_profile_exists():
    builder = BillingContextBuilder(_FakeProfileService(_profile(number_of_patients=750)), _FakePatientRepository(None))

    context = await builder.build(user=_user(), patient_id=999, encounter_date=date(2026, 6, 1))

    assert context.physician.number_of_patients == 750
    assert context.physician.physician_type == "omnipraticien"
    assert context.physician.remuneration_type == "mixte"


async def test_reads_the_profile_effective_on_the_encounter_date_not_todays():
    profile_service = _FakeProfileService(_profile())
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))
    encounter_date = date(2024, 3, 1)

    await builder.build(user=_user(), patient_id=999, encounter_date=encounter_date)

    [(_user_arg, on_date)] = profile_service.as_of_calls
    assert on_date == encounter_date


async def test_falls_back_to_the_earliest_profile_when_the_encounter_predates_every_version():
    # as_of finds nothing (encounter older than the physician's first profile version, e.g.
    # a demo transcript predating their own onboarding) — context_builder.py falls back to
    # the earliest version on file rather than leaving the physician side unresolved.
    profile_service = _FakeProfileService(None, earliest=_profile(number_of_patients=640))
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))

    context = await builder.build(user=_user(), patient_id=999, encounter_date=date(2020, 1, 1))

    assert context.physician.number_of_patients == 640


async def test_does_not_fall_back_to_earliest_when_as_of_already_found_a_profile():
    profile_service = _FakeProfileService(_profile(number_of_patients=320), earliest=_profile(number_of_patients=999))
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))

    context = await builder.build(user=_user(), patient_id=999, encounter_date=date(2026, 6, 1))

    assert context.physician.number_of_patients == 320
    assert profile_service.earliest_calls == []


async def test_a_patient_lookup_miss_degrades_to_no_patient_context():
    # PatientRepository.get can return None (deleted, unknown id) — this must not raise,
    # just leave the patient half unknown.
    builder = BillingContextBuilder(_FakeProfileService(None), _FakePatientRepository(None))

    context = await builder.build(user=_user(), patient_id=999, encounter_date=date(2026, 6, 1))

    assert context.patient.age_years is None


async def test_matched_patient_supplies_vulnerability():
    builder = BillingContextBuilder(_FakeProfileService(None), _FakePatientRepository(_patient(is_vulnerable=True)))

    context = await builder.build(user=_user(), patient_id=PATIENT_ID, encounter_date=date(2026, 6, 1))

    assert context.patient.is_vulnerable is True


async def test_matched_patient_age_is_computed_exactly_as_of_the_encounter_date():
    # Born 1968-03-10; on 2026-03-09 (a day before the birthday) they are still 57, not 58 —
    # pins the day/month boundary logic, not just the year subtraction.
    builder = BillingContextBuilder(
        _FakeProfileService(None), _FakePatientRepository(_patient(date_of_birth=date(1968, 3, 10)))
    )

    context = await builder.build(user=_user(), patient_id=PATIENT_ID, encounter_date=date(2026, 3, 9))

    assert context.patient.age_years == 57.0


async def test_missing_encounter_date_falls_back_to_today_for_the_profile_lookup():
    profile_service = _FakeProfileService(_profile())
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))

    context = await builder.build(user=_user(), patient_id=999, encounter_date=None)

    [(_user_arg, on_date)] = profile_service.as_of_calls
    assert on_date == date.today()
    assert context.encounter_date is None


# --- is_registered: derived from matching family_doctor_practice_number against the
# billing physician's own practice_number (app/patients/registration.py), not a stored
# roster flag. ---


async def test_registration_true_when_practice_numbers_match():
    builder = BillingContextBuilder(
        _FakeProfileService(None),
        _FakePatientRepository(_patient(family_doctor_practice_number="123456")),
    )

    context = await builder.build(
        user=_user(practice_number="123456"), patient_id=PATIENT_ID, encounter_date=date(2026, 6, 1)
    )

    assert context.patient.is_registered is True


async def test_registration_false_when_practice_numbers_differ():
    builder = BillingContextBuilder(
        _FakeProfileService(None),
        _FakePatientRepository(_patient(family_doctor_practice_number="111111")),
    )

    context = await builder.build(
        user=_user(practice_number="222222"), patient_id=PATIENT_ID, encounter_date=date(2026, 6, 1)
    )

    assert context.patient.is_registered is False


async def test_registration_unknown_when_patient_has_no_family_doctor_practice_number():
    builder = BillingContextBuilder(
        _FakeProfileService(None),
        _FakePatientRepository(_patient(family_doctor_practice_number=None)),
    )

    context = await builder.build(
        user=_user(practice_number="123456"), patient_id=PATIENT_ID, encounter_date=date(2026, 6, 1)
    )

    assert context.patient.is_registered is None


async def test_registration_unknown_when_physician_has_no_practice_number():
    builder = BillingContextBuilder(
        _FakeProfileService(None),
        _FakePatientRepository(_patient(family_doctor_practice_number="123456")),
    )

    context = await builder.build(
        user=_user(practice_number=None), patient_id=PATIENT_ID, encounter_date=date(2026, 6, 1)
    )

    assert context.patient.is_registered is None
