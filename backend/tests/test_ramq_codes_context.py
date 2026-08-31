"""Unit tests for BillingContextBuilder (app/ramq_codes/context_builder.py), isolated from
the real ProfileService/PatientRepository via small fakes — same convention as
test_ramq_codes_task.py's _FakeRetriever. Constructs User/Patient (plain SQLAlchemy
declarative models) directly rather than through a DB session: attribute access alone
doesn't need a session, and these tests have nothing to do with persistence."""

from datetime import date

from app.auth.profile import PhysicianAccount
from app.postgresdb import Gender, Patient, PhysicianProfile, User, UserRole
from app.ramq_codes.context import BillingContext
from app.ramq_codes.context_builder import BillingContextBuilder


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

    async def get_for_physician(self, patient_id: int, physician_id: int) -> Patient | None:
        return self._patient


def _user() -> User:
    return User(id=1, email="doc@example.test", hashed_password="x", full_name="Dr. Doe", role=UserRole.PHYSICIAN)


def _profile(**overrides) -> PhysicianProfile:
    defaults = dict(
        id=1, user_id=1, effective_from=date(2026, 1, 1),
        physician_type="omnipraticien", number_of_patients=320, remuneration_type="mixte",
    )
    return PhysicianProfile(**{**defaults, **overrides})


def _patient(**overrides) -> Patient:
    defaults = dict(
        id=2, physician_id=1, full_name="Jean Tremblay", date_of_birth=date(1968, 3, 10),
        gender=Gender.MALE, is_registered_with_physician=True, is_vulnerable=False,
    )
    return Patient(**{**defaults, **overrides})


async def test_no_profile_and_no_match_yields_an_all_null_context():
    builder = BillingContextBuilder(_FakeProfileService(None), _FakePatientRepository(None))

    context = await builder.build(user=_user(), matched_patient_id=None, encounter_date=date(2026, 6, 1))

    assert context.physician.number_of_patients is None
    assert context.patient.age_years is None
    assert context.patient.is_registered is None
    assert context.patient.is_vulnerable is None


async def test_profile_facts_carry_through_when_a_profile_exists():
    builder = BillingContextBuilder(_FakeProfileService(_profile(number_of_patients=750)), _FakePatientRepository(None))

    context = await builder.build(user=_user(), matched_patient_id=None, encounter_date=date(2026, 6, 1))

    assert context.physician.number_of_patients == 750
    assert context.physician.physician_type == "omnipraticien"
    assert context.physician.remuneration_type == "mixte"


async def test_reads_the_profile_effective_on_the_encounter_date_not_todays():
    profile_service = _FakeProfileService(_profile())
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))
    encounter_date = date(2024, 3, 1)

    await builder.build(user=_user(), matched_patient_id=None, encounter_date=encounter_date)

    [(_user_arg, on_date)] = profile_service.as_of_calls
    assert on_date == encounter_date


async def test_falls_back_to_the_earliest_profile_when_the_encounter_predates_every_version():
    # as_of finds nothing (encounter older than the physician's first profile version, e.g.
    # a demo transcript predating their own onboarding) — context_builder.py falls back to
    # the earliest version on file rather than leaving the physician side unresolved.
    profile_service = _FakeProfileService(None, earliest=_profile(number_of_patients=640))
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))

    context = await builder.build(user=_user(), matched_patient_id=None, encounter_date=date(2020, 1, 1))

    assert context.physician.number_of_patients == 640


async def test_does_not_fall_back_to_earliest_when_as_of_already_found_a_profile():
    profile_service = _FakeProfileService(_profile(number_of_patients=320), earliest=_profile(number_of_patients=999))
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))

    context = await builder.build(user=_user(), matched_patient_id=None, encounter_date=date(2026, 6, 1))

    assert context.physician.number_of_patients == 320
    assert profile_service.earliest_calls == []


async def test_no_matched_patient_leaves_patient_context_null_even_with_a_roster():
    builder = BillingContextBuilder(_FakeProfileService(None), _FakePatientRepository(_patient()))

    context = await builder.build(user=_user(), matched_patient_id=None, encounter_date=date(2026, 6, 1))

    assert context.patient.is_registered is None


async def test_matched_patient_supplies_registration_and_vulnerability():
    builder = BillingContextBuilder(
        _FakeProfileService(None),
        _FakePatientRepository(_patient(is_registered_with_physician=True, is_vulnerable=True)),
    )

    context = await builder.build(user=_user(), matched_patient_id=2, encounter_date=date(2026, 6, 1))

    assert context.patient.is_registered is True
    assert context.patient.is_vulnerable is True


async def test_matched_patient_age_is_computed_exactly_as_of_the_encounter_date():
    # Born 1968-03-10; on 2026-03-09 (a day before the birthday) they are still 57, not 58 —
    # pins the day/month boundary logic, not just the year subtraction.
    builder = BillingContextBuilder(
        _FakeProfileService(None), _FakePatientRepository(_patient(date_of_birth=date(1968, 3, 10)))
    )

    context = await builder.build(user=_user(), matched_patient_id=2, encounter_date=date(2026, 3, 9))

    assert context.patient.age_years == 57.0


async def test_a_stale_matched_patient_id_degrades_to_no_patient_context():
    # PatientRepository.get_for_physician can return None (soft-deleted, wrong physician) —
    # this must not raise, just leave the patient half unknown, same best-effort stance as
    # PatientSuggestionService's own matcher-failure handling.
    builder = BillingContextBuilder(_FakeProfileService(None), _FakePatientRepository(None))

    context = await builder.build(user=_user(), matched_patient_id=999, encounter_date=date(2026, 6, 1))

    assert context.patient.age_years is None


async def test_missing_encounter_date_falls_back_to_today_for_the_profile_lookup():
    profile_service = _FakeProfileService(_profile())
    builder = BillingContextBuilder(profile_service, _FakePatientRepository(None))

    context = await builder.build(user=_user(), matched_patient_id=None, encounter_date=None)

    [(_user_arg, on_date)] = profile_service.as_of_calls
    assert on_date == date.today()
    assert context.encounter_date is None
