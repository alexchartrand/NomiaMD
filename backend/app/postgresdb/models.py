"""ORM shapes only — persistence lives in repository.py (UserRepository/
ExtractionRepository), not here."""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.postgresdb.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PHYSICIAN = "physician"


class PhysicianType(str, enum.Enum):
    """Placeholder list — refine once the exact set of practice settings is confirmed."""

    MED_FAM = "Médecin de famille"
    SPECIALIST = "Spécialiste"
    AUTRE = "Autre"


class User(Base):
    """A manually-provisioned login (see scripts/create_user.py — there is no signup path).
    `is_active` lets an account be revoked instantly without deleting its history; it's
    checked on every request (app/auth/dependencies.py), not just at login."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.PHYSICIAN)
    physician_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    number_of_patients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Gender(str, enum.Enum):
    """Placeholder list — refine once the exact set needed is confirmed."""

    MALE = "M"
    FEMALE = "F"
    OTHER = "Autre"


class Patient(Base):
    """A physician's own patient roster — distinct from sample_patients.py's synthetic
    demo transcripts. Holds administrative facts (registration status, vulnerability) that
    billing_codes needs but can never derive from a transcript (see CLAUDE.md)."""

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    ramq_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender), nullable=True)
    is_registered_with_physician: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vulnerable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ExtractionRecord(Base):
    """One stored extraction run. `transcript` is kept only long enough for physician
    review — set up a retention/purge job before this holds real patient data; see the
    compliance note in the top-level README."""

    __tablename__ = "extraction_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(64))
    transcript: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
