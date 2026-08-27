"""ORM shapes only — persistence lives in repository.py (UserRepository/
ExtractionRepository), not here."""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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


class RemunerationType(str, enum.Enum):
    MIXTE = "Mixte"
    A_L_ACTE = "À l'acte"


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
    remuneration_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Gender(str, enum.Enum):
    """Placeholder list — refine once the exact set needed is confirmed."""

    MALE = "M"
    FEMALE = "F"
    OTHER = "X"


class Patient(Base):
    """A physician's own patient roster — distinct from app/sample_patients/'s synthetic
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
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
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


class Claim(Base):
    """One physician-confirmed RAMQ claim for an encounter, with many code lines
    (ClaimCode). `status` is a plain string, not a SQLAlchemy Enum — see the note in
    docs/plans/billing-workflow.md, Part 5: with no Alembic, adding a status value later must
    not require an `ALTER TYPE` on the prod Postgres box, so the allowed set is enforced by a
    Pydantic Literal at the API boundary instead."""

    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_physician_service_date", "physician_id", "service_date"),
        UniqueConstraint("billing_extraction_record_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="brouillon")
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_extraction_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_records.id"), nullable=True
    )
    billing_extraction_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_records.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ClaimCode(Base):
    """One selected RAMQ code on a claim. Fields are a snapshot of the candidate at
    save time (not a live join back to the LanceDB `codes` table), because that table is a
    regenerated external artifact — re-deriving a historical claim's fee/rules would
    silently rewrite history whenever the tariff data changes."""

    __tablename__ = "claim_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    fee_amount: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)
    fee_when_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    majoration: Mapped[str | None] = mapped_column(Text, nullable=True)


class Bill(Base):
    """One generated invoice grouping many claims over a date range. The PDF is
    rendered on demand from the linked claims (which are themselves already snapshots —
    see ClaimCode), so nothing is stored as bytes; total_amount/record_count are
    snapshotted anyway so listing bills never has to re-sum every claim's codes."""

    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    total_amount: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer)


class BillClaim(Base):
    """Association table linking a Bill to the claims it covers, rather than a
    bill_id column on Claim — with no Alembic (see Claim's docstring), a new
    table is created for free by create_all while a new column on an existing table is not.
    The unique index on claim_id is the DB-level guarantee that a claim can never
    land on two bills at once."""

    __tablename__ = "bill_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), index=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id"), unique=True, index=True
    )
