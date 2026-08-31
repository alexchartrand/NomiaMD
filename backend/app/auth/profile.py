"""Profile use case: reads and writes a physician's editable practice facts.

Split from AuthService deliberately — that class owns authentication (credentials,
tokens, sessions); this one owns the physician's practice facts, which are billing
domain data that merely happen to be edited from the account screen. The two write to
different tables with different lifecycles: `users` is credentials, `physician_profiles`
is an append-only history (see the model's docstring for why).
"""

from dataclasses import dataclass
from datetime import date

from app.postgresdb import (
    PhysicianProfile,
    PhysicianProfileRepository,
    User,
    UserRepository,
)


@dataclass(frozen=True)
class PhysicianAccount:
    """A user together with the profile version that applies — what the API presents as
    one flat object, kept as two so callers can't confuse the credential record with the
    dated practice facts. `profile` is None for a physician who never filled one in."""

    user: User
    profile: PhysicianProfile | None


class ProfileService:
    def __init__(
        self,
        user_repository: UserRepository,
        profile_repository: PhysicianProfileRepository,
    ) -> None:
        self._users = user_repository
        self._profiles = profile_repository

    async def current(self, user: User) -> PhysicianAccount:
        """The account as of today — what the profile screen shows."""
        return PhysicianAccount(user=user, profile=await self._profiles.get_current(user.id))

    async def as_of(self, user: User, on: date) -> PhysicianAccount:
        """The account as it stood on `on`. Use this, not `current`, when interpreting a
        past encounter: whether a code was billable depends on the physician's
        remuneration type and panel size at the time of service, not today's."""
        return PhysicianAccount(user=user, profile=await self._profiles.get_effective_on(user.id, on))

    async def earliest(self, user: User) -> PhysicianAccount:
        """The physician's very first profile version on file, regardless of date. Not a
        substitute for `as_of` — only app/ramq_codes/context_builder.py's best-effort
        fallback should call this, for an encounter dated before any version had taken
        effect (see PhysicianProfileRepository.get_earliest's docstring)."""
        return PhysicianAccount(user=user, profile=await self._profiles.get_earliest(user.id))

    async def update(
        self,
        user: User,
        *,
        full_name: str,
        physician_type: str | None,
        number_of_patients: int | None,
        remuneration_type: str | None,
    ) -> PhysicianAccount:
        """Writes both halves: the name onto `users`, the practice facts as a new
        profile version taking effect today."""
        updated = await self._users.update_full_name(user.id, full_name)
        if updated is None:
            raise RuntimeError(f"user {user.id} vanished mid-request")
        profile = await self._profiles.upsert_current(
            user.id,
            physician_type=physician_type,
            number_of_patients=number_of_patients,
            remuneration_type=remuneration_type,
        )
        return PhysicianAccount(user=updated, profile=profile)
