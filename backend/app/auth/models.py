"""Auth request/response models — same style as app/models.py."""

from pydantic import BaseModel

from app.postgresdb import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    """Never includes hashed_password."""

    id: int
    email: str
    full_name: str
    role: UserRole
    physician_type: str | None
    number_of_patients: int | None

    model_config = {"from_attributes": True}
