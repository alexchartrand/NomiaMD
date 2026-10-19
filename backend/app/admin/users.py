"""Account management from the admin console: provisioning, edits, deactivation, password
resets and session revocation. Accounts are never deleted (they own encounters, claims and
bills), only deactivated, which is reversible.

Every change is written to the audit trail in the same transaction as the change itself
(SessionAuditLog), so the trail never shows a change that was rolled back. Temporary
passwords are returned once to the caller and never logged or stored in clear."""

import asyncio
from dataclasses import dataclass

from app.admin.passwords import TemporaryPasswordGenerator
from app.audit import AuditAction, AuditEntry, IAuditLog
from app.auth.profile import PhysicianAccount, PracticeFacts, ProfileService
from app.auth.security import PasswordHasher
from app.postgresdb import AccountActivity, User, UserRepository, UserRole


_PRACTICE_FACT_FIELDS = {"physician_type", "panel_size", "remuneration_type"}


class UserNotFoundError(LookupError):
    pass


class AdminGuardError(Exception):
    """The change would lock the console out: an admin removing their own access, or the
    last active admin being deactivated or demoted. The message is shown to the admin."""


@dataclass(frozen=True)
class NewAccount:
    email: str
    full_name: str
    role: UserRole
    practice_number: str | None = None
    facts: PracticeFacts | None = None


@dataclass(frozen=True)
class AccountChanges:
    full_name: str
    role: UserRole
    practice_number: str | None
    facts: PracticeFacts


@dataclass(frozen=True)
class AdminAccount:
    """What the console lists for one account: the user, the practice facts in effect today
    and how much work hangs off it."""

    account: PhysicianAccount
    activity: AccountActivity


@dataclass(frozen=True)
class IssuedPassword:
    account: AdminAccount
    temporary_password: str


class UserAdminService:
    def __init__(
        self,
        user_repository: UserRepository,
        profile_service: ProfileService,
        password_hasher: PasswordHasher,
        password_generator: TemporaryPasswordGenerator,
        audit_log: IAuditLog,
    ) -> None:
        self._users = user_repository
        self._profiles = profile_service
        self._hasher = password_hasher
        self._passwords = password_generator
        self._audit = audit_log

    async def list_accounts(self) -> list[AdminAccount]:
        users = await self._users.list_all()
        activity = await self._users.activity_by_user()
        return [await self._present(user, activity.get(user.id, AccountActivity())) for user in users]

    async def get_account(self, user_id: int) -> AdminAccount:
        return await self._present_one(await self._require(user_id))

    async def create(self, actor: User, new: NewAccount) -> IssuedPassword:
        """Raises DuplicateEmailError / DuplicatePracticeNumberError (app/postgresdb)."""
        temporary = self._passwords.generate()
        user = await self._users.create(
            email=new.email,
            hashed_password=await self._hash(temporary),
            full_name=new.full_name,
            role=new.role,
            practice_number=new.practice_number,
            must_change_password=True,
        )
        if new.facts is not None:
            await self._profiles.record_practice_facts(user.id, new.facts)
        await self._record(AuditAction.USER_CREATED, actor, user, {"role": new.role.value})
        return IssuedPassword(await self._present_one(user), temporary)

    async def update(self, actor: User, user_id: int, changes: AccountChanges) -> AdminAccount:
        user = await self._require(user_id)
        # Values, not the account: `user` is the same ORM object the update mutates.
        before = _editable_values(await self._profiles.current(user))
        if changes.role != user.role:
            await self._guard_admin_removal(actor, user, "retirer le rôle administrateur")
            old_role = user.role
            await self._users.set_role(user.id, changes.role)
            await self._record(
                AuditAction.USER_ROLE_CHANGED, actor, user, {"from": old_role.value, "to": changes.role.value}
            )
        changed = _changed_fields(before, changes)
        if set(changed) & _PRACTICE_FACT_FIELDS:
            await self._profiles.update(
                user, full_name=changes.full_name, practice_number=changes.practice_number, facts=changes.facts
            )
        elif changed:
            # Name or practice number only: no new practice-facts version for an unchanged one.
            await self._users.update_editable_fields(
                user.id, full_name=changes.full_name, practice_number=changes.practice_number
            )
        if changed:
            await self._record(AuditAction.USER_UPDATED, actor, user, {"fields": changed})
        return await self._present_one(user)

    async def deactivate(self, actor: User, user_id: int) -> AdminAccount:
        user = await self._require(user_id)
        if user.is_active:
            await self._guard_admin_removal(actor, user, "désactiver")
            await self._users.set_active(user.id, False)
            await self._record(AuditAction.USER_DEACTIVATED, actor, user)
        return await self._present_one(user)

    async def reactivate(self, actor: User, user_id: int) -> AdminAccount:
        user = await self._require(user_id)
        if not user.is_active:
            await self._users.set_active(user.id, True)
            await self._record(AuditAction.USER_REACTIVATED, actor, user)
        return await self._present_one(user)

    async def reset_password(self, actor: User, user_id: int) -> IssuedPassword:
        """Replaces the password with a temporary one and ends every open session."""
        user = await self._require(user_id)
        if user.id == actor.id:
            raise AdminGuardError("Changez votre propre mot de passe depuis votre profil.")
        temporary = self._passwords.generate()
        await self._users.set_password(user.id, await self._hash(temporary), must_change=True)
        await self._record(AuditAction.USER_PASSWORD_RESET, actor, user)
        return IssuedPassword(await self._present_one(user), temporary)

    async def revoke_sessions(self, actor: User, user_id: int) -> None:
        user = await self._require(user_id)
        await self._users.bump_session_version(user.id)
        await self._record(AuditAction.USER_SESSIONS_REVOKED, actor, user)

    async def _guard_admin_removal(self, actor: User, target: User, verb: str) -> None:
        if target.role != UserRole.ADMIN:
            return
        if target.id == actor.id:
            raise AdminGuardError(f"Vous ne pouvez pas {verb} votre propre compte.")
        if target.is_active and await self._users.count_active_admins() <= 1:
            raise AdminGuardError(f"Impossible de {verb} le dernier administrateur actif.")

    async def _require(self, user_id: int) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def _present_one(self, user: User) -> AdminAccount:
        activity = await self._users.activity_by_user()
        return await self._present(user, activity.get(user.id, AccountActivity()))

    async def _present(self, user: User, activity: AccountActivity) -> AdminAccount:
        return AdminAccount(account=await self._profiles.current(user), activity=activity)

    async def _hash(self, password: str) -> str:
        # Argon2 is CPU-slow by design; keep it off the event loop (see AuthService._verify).
        return await asyncio.to_thread(self._hasher.hash, password)

    async def _record(self, action: AuditAction, actor: User, target: User, details: dict | None = None) -> None:
        await self._audit.record(AuditEntry(action, actor_id=actor.id, target_user_id=target.id, details=details))


def _editable_values(account: PhysicianAccount) -> dict:
    profile = account.profile
    return {
        "full_name": account.user.full_name,
        "practice_number": account.user.practice_number,
        "physician_type": profile.physician_type if profile else None,
        "panel_size": profile.panel_size if profile else None,
        "remuneration_type": profile.remuneration_type if profile else None,
    }


def _changed_fields(before: dict, changes: AccountChanges) -> list[str]:
    """Names only, never values — the trail says what was edited, not the data itself."""
    after = {
        "full_name": changes.full_name,
        "practice_number": changes.practice_number,
        "physician_type": changes.facts.physician_type,
        "panel_size": changes.facts.panel_size,
        "remuneration_type": changes.facts.remuneration_type,
    }
    return [name for name in before if before[name] != after[name]]
