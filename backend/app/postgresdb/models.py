"""ORM shapes only — persistence lives in repository.py (UserRepository/
ExtractionRepository), not here."""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    Identity and credentials only: the physician's editable practice facts live in
    PhysicianProfile, so this table stays small and rarely-written. `is_active` lets an
    account be revoked instantly without deleting its history; it's checked on every
    request (app/auth/dependencies.py), not just at login."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.PHYSICIAN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhysicianProfile(Base):
    """A physician's practice facts, as of a date — append-only, one row per edit rather
    than one row per physician.

    These aren't user preferences: `remuneration_type` (mixte vs à l'acte),
    `physician_type` and `number_of_patients` are administrative facts that decide which
    RAMQ codes a physician may legally bill, and they change over a career. Keeping them
    as mutable columns on `users` meant editing the profile silently rewrote the basis of
    every past claim — the same failure ClaimCode's fee snapshot exists to prevent. A
    claim must stay interpretable under the values in effect on its own service_date, so
    read it with `get_effective_on(user_id, service_date)`, not `get_current`.

    New editable fields are added here as nullable columns; `users` doesn't grow.
    """

    __tablename__ = "physician_profiles"
    __table_args__ = (Index("ix_physician_profiles_user_effective", "user_id", "effective_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The date this version took effect. Rows are never updated except within the same
    # day (see PhysicianProfileRepository.upsert_current) — there is no meaningful
    # history between two edits made an hour apart.
    effective_from: Mapped[date] = mapped_column(Date)
    physician_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    number_of_patients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remuneration_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )


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
    __table_args__ = (
        # Lets claims reference (patient_id, physician_id) as a composite FK, so the DB
        # itself rejects billing a patient onto a physician they aren't rostered under —
        # not just ClaimService's application-level check.
        UniqueConstraint("id", "physician_id"),
        # Partial (not table-wide) so a soft-deleted patient never blocks re-adding the
        # same NAM, or a later correction of a duplicate. NULL ramq_number never
        # collides either way — both dialects already treat NULLs as distinct in a
        # unique index. Live on both dialects (unlike the FK ondelete/composite-FK
        # items) since SQLite enforces unique indexes unconditionally, no PRAGMA needed.
        Index(
            "ix_patients_physician_ramq_number_active",
            "physician_id",
            "ramq_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    ramq_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender), nullable=True)
    is_registered_with_physician: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vulnerable: Mapped[bool] = mapped_column(Boolean, default=False)
    # Nullable timestamp rather than a bool: under Law 25 the deletion date is the thing
    # an audit asks for, not just whether the patient is gone. `IS NULL`/`IS NOT NULL`
    # filters identically to the old is_deleted flag.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class ExtractionRecord(Base):
    """One stored extraction run. `transcript` is kept only long enough for physician
    review — set up a retention/purge job before this holds real patient data; see the
    compliance note in the top-level README."""

    __tablename__ = "extraction_records"
    __table_args__ = (Index("ix_extraction_records_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(64))
    transcript: Mapped[str] = mapped_column(Text)
    # JSON on SQLite (dev), JSONB on Postgres: keeps the retention purge and
    # "which extractions mention this NAM" query indexable instead of a full-table LIKE.
    result_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    model: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
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
        # Composite FK against patients(id, physician_id): the DB rejects a claim whose
        # patient_id/physician_id pairing doesn't match an actual roster row, closing the
        # gap where only ClaimService enforced "this patient belongs to this physician".
        ForeignKeyConstraint(
            ["patient_id", "physician_id"],
            ["patients.id", "patients.physician_id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[int] = mapped_column(index=True)
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
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class ClaimCode(Base):
    """One selected RAMQ code on a claim. Fields are a snapshot of the candidate at
    save time (not a live join back to the LanceDB `codes` table), because that table is a
    regenerated external artifact — re-deriving a historical claim's fee/rules would
    silently rewrite history whenever the tariff data changes."""

    __tablename__ = "claim_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_when_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    majoration: Mapped[str | None] = mapped_column(Text, nullable=True)


class Bill(Base):
    """One generated invoice grouping many claims over a date range. The PDF is
    rendered on demand from the linked claims (which are themselves already snapshots —
    see ClaimCode), so nothing is stored as bytes; total_amount/record_count are
    snapshotted anyway so listing bills never has to re-sum every claim's codes."""

    __tablename__ = "bills"
    __table_args__ = (Index("ix_bills_physician_start_date", "physician_id", "start_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer)


class BillClaim(Base):
    """Association table linking a Bill to the claims it covers, rather than a
    bill_id column on Claim — with no Alembic (see Claim's docstring), a new
    table is created for free by create_all while a new column on an existing table is not.
    The unique index on claim_id is the DB-level guarantee that a claim can never
    land on two bills at once."""

    __tablename__ = "bill_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), unique=True, index=True
    )
