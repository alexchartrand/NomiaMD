"""BillingContextBuilder (app/ramq_codes/context_builder.py) run inside its own short DB
transaction — the pipeline's default context builder.

The billing_codes pipeline sits between two multi-second LLM calls, so it can't borrow a
request-scoped session without holding a pooled connection (and an open transaction) across
both of them. This opens one only for the profile/patient reads and closes it before the
billing_codes call starts. Same `build(...)` signature as BillingContextBuilder, so tests
can still hand the pipeline a fake."""

from datetime import date

from app.auth.factory import build_profile_service
from app.care_setting import CareSetting
from app.postgresdb import PatientRepository, User, session_scope
from app.ramq_codes import BillingContext, BillingContextBuilder


class ScopedBillingContextBuilder:
    async def build(
        self,
        *,
        user: User,
        patient_id: int,
        encounter_date: date | None,
        care_setting: CareSetting | None = None,
    ) -> BillingContext:
        async with session_scope() as session:
            builder = BillingContextBuilder(build_profile_service(session), PatientRepository(session))
            return await builder.build(
                user=user, patient_id=patient_id, encounter_date=encounter_date, care_setting=care_setting
            )
