"""Admin console request/response models. Mirrored by hand in frontend/src/api/admin.ts."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.admin.users import AdminAccount
from app.auth.profile import PracticeFacts
from app.postgresdb import PhysicianType, RemunerationType, UserRole

_PRACTICE_NUMBER_PATTERN = r"^\d{5,6}$"
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class AdminUserOut(BaseModel):
    """Never includes the password hash."""

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    practice_number: str | None
    physician_type: PhysicianType | None
    panel_size: int | None
    remuneration_type: RemunerationType | None
    created_at: datetime
    last_login_at: datetime | None
    deactivated_at: datetime | None
    encounter_count: int
    claim_count: int

    @classmethod
    def from_admin_account(cls, admin_account: AdminAccount) -> "AdminUserOut":
        user = admin_account.account.user
        profile = admin_account.account.profile
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            must_change_password=bool(user.must_change_password),
            practice_number=user.practice_number,
            physician_type=profile.physician_type if profile else None,
            panel_size=profile.panel_size if profile else None,
            remuneration_type=profile.remuneration_type if profile else None,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            deactivated_at=user.deactivated_at,
            encounter_count=admin_account.activity.encounters,
            claim_count=admin_account.activity.claims,
        )


class _AccountFields(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.PHYSICIAN
    practice_number: str | None = Field(default=None, pattern=_PRACTICE_NUMBER_PATTERN)
    physician_type: PhysicianType | None = None
    panel_size: int | None = Field(default=None, ge=0)
    remuneration_type: RemunerationType | None = None

    def practice_facts(self) -> PracticeFacts:
        return PracticeFacts(
            physician_type=self.physician_type.value if self.physician_type else None,
            panel_size=self.panel_size,
            remuneration_type=self.remuneration_type.value if self.remuneration_type else None,
        )

    def has_practice_facts(self) -> bool:
        return any(v is not None for v in (self.physician_type, self.panel_size, self.remuneration_type))


class AdminUserCreate(_AccountFields):
    email: str = Field(max_length=255, pattern=_EMAIL_PATTERN)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class AdminUserUpdate(_AccountFields):
    pass


class TemporaryPasswordOut(BaseModel):
    """Shown to the admin once, to hand over to the user — never retrievable again."""

    user: AdminUserOut
    temporary_password: str
