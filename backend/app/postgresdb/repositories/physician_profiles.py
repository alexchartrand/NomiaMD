"""`physician_profiles` — the dated history of a physician's practice facts."""

from datetime import date

from sqlalchemy import select

from app.postgresdb.models import PhysicianProfile
from app.postgresdb.repositories.base import SessionRepository


class PhysicianProfileRepository(SessionRepository):
    """Append-only history of a physician's practice facts (see PhysicianProfile). Reads
    are "which version applies on date D", never a plain column read. What "today" is, and
    when an edit overwrites a version instead of adding one, is ProfileService's call
    (app/auth/profile.py)."""

    async def get_effective_on(self, user_id: int, on: date) -> PhysicianProfile | None:
        """The version in effect on `on` — the latest row that had already taken effect by
        then. Returns None when the physician had no profile yet at that date, which is
        also the answer for a physician who has never filled one in.

        Ties on effective_from break by id so a same-day backfill is deterministic."""
        result = await self._session.execute(
            select(PhysicianProfile)
            .where(
                PhysicianProfile.user_id == user_id,
                PhysicianProfile.effective_from <= on,
            )
            .order_by(PhysicianProfile.effective_from.desc(), PhysicianProfile.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_earliest(self, user_id: int) -> PhysicianProfile | None:
        """The physician's very first profile version, regardless of date — a best-effort
        fallback for an encounter dated before any version had taken effect (e.g. a demo
        transcript predating a freshly-onboarded physician's own profile entry), used only
        by app/ramq_codes/context_builder.py's BillingContext resolution. Never used for fee
        calculation (app/bills/service.py keeps calling get_effective_on directly), since a
        bill's fee snapshot must stay strictly historically accurate — this method exists so
        billing_codes has *something* to suggest from instead of leaving the panel-size axis
        unresolved purely because the physician's account is newer than the encounter."""
        result = await self._session.execute(
            select(PhysicianProfile)
            .where(PhysicianProfile.user_id == user_id)
            .order_by(PhysicianProfile.effective_from.asc(), PhysicianProfile.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_starting_on(self, user_id: int, effective_from: date) -> PhysicianProfile | None:
        """The version that takes effect exactly on `effective_from`, if any."""
        result = await self._session.execute(
            select(PhysicianProfile).where(
                PhysicianProfile.user_id == user_id,
                PhysicianProfile.effective_from == effective_from,
            )
        )
        return result.scalars().first()

    async def add(
        self,
        user_id: int,
        *,
        effective_from: date,
        physician_type: str | None,
        number_of_patients: int | None,
        remuneration_type: str | None,
    ) -> PhysicianProfile:
        profile = PhysicianProfile(
            user_id=user_id,
            effective_from=effective_from,
            physician_type=physician_type,
            number_of_patients=number_of_patients,
            remuneration_type=remuneration_type,
        )
        self._session.add(profile)
        await self._session.flush()
        await self._session.refresh(profile)
        return profile

    async def overwrite(
        self,
        profile: PhysicianProfile,
        *,
        physician_type: str | None,
        number_of_patients: int | None,
        remuneration_type: str | None,
    ) -> PhysicianProfile:
        profile.physician_type = physician_type
        profile.number_of_patients = number_of_patients
        profile.remuneration_type = remuneration_type
        await self._session.flush()
        await self._session.refresh(profile)
        return profile
