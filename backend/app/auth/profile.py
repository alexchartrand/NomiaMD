"""Profile use case: reads and writes a physician's editable practice facts.

Split from AuthService deliberately — that class owns authentication (credentials,
tokens, sessions); this one owns the physician's practice facts, which are billing
domain data that merely happen to be edited from the account screen. The two write to
different tables with different lifecycles: `users` is credentials, `physician_profiles`
is an append-only history (see the model's docstring for why).
"""

from dataclasses import asdict, dataclass
from datetime import date

from app.clock import ClinicClock, Clock
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


@dataclass(frozen=True)
class PracticeFacts:
    """The editable practice facts one physician_profiles version records."""

    physician_type: str | None
    number_of_patients: int | None
    remuneration_type: str | None


class ProfileService:
    def __init__(
        self,
        user_repository: UserRepository,
        profile_repository: PhysicianProfileRepository,
        clock: Clock | None = None,
    ) -> None:
        self._users = user_repository
        self._profiles = profile_repository
        self._clock = clock or ClinicClock()

    async def current(self, user: User) -> PhysicianAccount:
        """The account as of today — what the profile screen shows."""
        return await self.as_of(user, self._clock.today())

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

    async def record_practice_facts(
        self, user_id: int, facts: PracticeFacts, *, effective_from: date | None = None
    ) -> PhysicianProfile:
        """Records `facts` as the version taking effect on `effective_from` (default: today,
        in the clinic's timezone).

        Appends a new version, except when one already takes effect on that same date —
        that one is overwritten in place. Two edits an hour apart are a correction, not two
        versions of reality, and keeping both would grow the table without ever changing
        the answer to `as_of`."""
        effective = effective_from or self._clock.today()
        existing = await self._profiles.get_starting_on(user_id, effective)
        if existing is None:
            return await self._profiles.add(user_id, effective_from=effective, **asdict(facts))
        return await self._profiles.overwrite(existing, **asdict(facts))

    async def update(
        self,
        user: User,
        *,
        full_name: str,
        practice_number: str | None,
        facts: PracticeFacts,
    ) -> PhysicianAccount:
        """Writes both halves: the name and practice_number onto `users`, the practice facts
        as a new profile version taking effect today. Both land in the caller's one
        transaction, so neither half is ever saved without the other."""
        updated = await self._users.update_editable_fields(
            user.id, full_name=full_name, practice_number=practice_number
        )
        if updated is None:
            raise RuntimeError(f"user {user.id} vanished mid-request")
        profile = await self.record_practice_facts(user.id, facts)
        return PhysicianAccount(user=updated, profile=profile)
