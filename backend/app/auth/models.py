"""Auth request/response models — same style as app/models.py."""

from pydantic import BaseModel, Field

from app.postgresdb import PhysicianType, UserRole


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class UserOut(BaseModel):
    """Never includes hashed_password."""

    id: int
    email: str
    full_name: str
    role: UserRole
    physician_type: str | None
    number_of_patients: int | None

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    full_name: str
    physician_type: PhysicianType | None = None
    number_of_patients: int | None = Field(default=None, ge=0)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
