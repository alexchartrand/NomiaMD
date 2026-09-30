"""`physician_profiles` — the dated history of a physician's practice facts."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite

from app.postgresdb.models import PhysicianProfile
from app.postgresdb.repositories.base import SessionRepository

# Both dialects spell INSERT ... ON CONFLICT DO UPDATE the same way, but through their own
# `insert` construct.
_DIALECT_INSERTS = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}


class PhysicianProfileRepository(SessionRepository):
    """Append-only history of a physician's practice facts (see PhysicianProfile). Reads
    are "which version applies on date D", never a plain column read. What "today" is is
    ProfileService's call (app/auth/profile.py)."""

    async def get_effective_on(self, user_id: int, on: date) -> PhysicianProfile | None:
        """The version in effect on `on` — the latest row that had already taken effect by
        then. Returns None when the physician had no profile yet at that date, which is
        also the answer for a physician who has never filled one in."""
        result = await self._session.execute(
            select(PhysicianProfile)
            .where(
                PhysicianProfile.user_id == user_id,
                PhysicianProfile.effective_from <= on,
            )
            .order_by(PhysicianProfile.effective_from.desc())
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
            .order_by(PhysicianProfile.effective_from.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        *,
        effective_from: date,
        physician_type: str | None,
        panel_size: int | None,
        remuneration_type: str | None,
    ) -> PhysicianProfile:
        """Adds the version taking effect on `effective_from`, or overwrites the one already
        there — one atomic statement, so two concurrent same-day saves can't both insert."""
        facts = {
            "physician_type": physician_type,
            "panel_size": panel_size,
            "remuneration_type": remuneration_type,
        }
        insert = _DIALECT_INSERTS[self._session.bind.dialect.name]
        statement = (
            insert(PhysicianProfile)
            .values(user_id=user_id, effective_from=effective_from, **facts)
            .on_conflict_do_update(
                index_elements=[PhysicianProfile.user_id, PhysicianProfile.effective_from],
                set_={**facts, "updated_at": func.now()},
            )
            .returning(PhysicianProfile)
        )
        # populate_existing: an overwritten version already loaded in this session must pick
        # up the new values rather than keep its stale ones from the identity map.
        result = await self._session.scalars(statement, execution_options={"populate_existing": True})
        return result.one()
