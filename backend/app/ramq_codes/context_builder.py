"""Assembles a BillingContext (context.py) from the physician's profile and the identified
patient's roster record — the business logic of "which administrative facts apply on this
encounter date", split from app/extraction/pipeline.py's orchestration and from
app/extraction/router.py's HTTP concerns, per this repo's one-class-one-job convention.

Constructor-injected with ProfileService and PatientRepository, not global lookups — makes
this class trivially fakeable in tests, same convention as PatientSuggestionService."""

from datetime import date

from app.auth.profile import ProfileService
from app.postgresdb import PatientRepository, User
from app.ramq_codes.context import BillingContext, PatientContext, PhysicianContext


def _age_years_on(date_of_birth: date, on_date: date) -> float:
    # Whole years is enough precision for the age-band axis (<70/<80/>=80) this feeds —
    # matches PatientSuggestionService/nam.py's own age-in-years granularity.
    years = on_date.year - date_of_birth.year
    if (on_date.month, on_date.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return float(years)


class BillingContextBuilder:
    def __init__(self, profile_service: ProfileService, patient_repository: PatientRepository):
        self._profiles = profile_service
        self._patients = patient_repository

    async def build(
        self,
        *,
        user: User,
        matched_patient_id: int | None,
        encounter_date: date | None,
    ) -> BillingContext:
        """Best-effort: a missing profile or an unmatched patient degrades that half to
        all-null rather than raising, mirroring extraction/router.py's existing "a matcher
        bug must never throw away a completed extraction" stance for the patient side, and
        extending it to the physician-profile side for the same reason."""
        on_date = encounter_date or date.today()

        account = await self._profiles.as_of(user, on_date)
        profile = account.profile
        if profile is None:
            # No profile version had taken effect yet as of the encounter date — most
            # commonly, the physician's very first profile was entered after this encounter
            # (e.g. a demo/backfilled transcript predating their own onboarding). Fall back
            # to the earliest version on file as a best-effort estimate rather than leaving
            # the whole physician side unresolved: still real physician-entered data, just
            # not provably in effect at this exact date. See BACKLOG.md — this trade-off
            # needs revalidation once physicians accumulate multiple profile versions.
            profile = (await self._profiles.earliest(user)).profile

        physician = (
            PhysicianContext(
                number_of_patients=profile.number_of_patients,
                physician_type=profile.physician_type,
                remuneration_type=profile.remuneration_type,
            )
            if profile is not None
            else PhysicianContext()
        )

        patient = PatientContext()
        if matched_patient_id is not None:
            record = await self._patients.get_for_physician(matched_patient_id, user.id)
            if record is not None:
                patient = PatientContext(
                    age_years=_age_years_on(record.date_of_birth, on_date),
                    is_registered=record.is_registered_with_physician,
                    is_vulnerable=record.is_vulnerable,
                )

        return BillingContext(physician=physician, patient=patient, encounter_date=encounter_date)
