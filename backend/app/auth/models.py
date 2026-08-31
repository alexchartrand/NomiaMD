"""Auth request/response models — same style as app/models.py."""

from pydantic import BaseModel, Field

from app.auth.profile import PhysicianAccount
from app.postgresdb import PhysicianType, RemunerationType, UserRole

_PRACTICE_NUMBER_PATTERN = r"^\d{5,6}$"


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class UserOut(BaseModel):
    """Never includes hashed_password.

    Flattens the two halves of a PhysicianAccount (`users` + the applicable
    `physician_profiles` row) into the single object the frontend already consumes —
    the storage split is a persistence concern, not an API change."""

    id: int
    email: str
    full_name: str
    role: UserRole
    physician_type: str | None
    number_of_patients: int | None
    remuneration_type: str | None
    practice_number: str | None

    @classmethod
    def from_account(cls, account: "PhysicianAccount") -> "UserOut":
        profile = account.profile
        return cls(
            id=account.user.id,
            email=account.user.email,
            full_name=account.user.full_name,
            role=account.user.role,
            physician_type=profile.physician_type if profile else None,
            number_of_patients=profile.number_of_patients if profile else None,
            remuneration_type=profile.remuneration_type if profile else None,
            # Unlike the rest of this method's fields, not sourced from `profile` — it
            # lives directly on `users` (see the User model's docstring for why).
            practice_number=account.user.practice_number,
        )


class ProfileUpdateRequest(BaseModel):
    full_name: str
    physician_type: PhysicianType | None = None
    number_of_patients: int | None = Field(default=None, ge=0)
    remuneration_type: RemunerationType | None = None
    practice_number: str | None = Field(default=None, pattern=_PRACTICE_NUMBER_PATTERN)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
