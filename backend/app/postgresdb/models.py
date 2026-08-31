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
    ForeignKey,
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
    request (app/auth/dependencies.py), not just at login.

    `practice_number` is the one exception to "practice facts live in PhysicianProfile":
    unlike panel size or remuneration type, a RAMQ practice number essentially never
    changes over a career, so it doesn't need PhysicianProfile's append-only history — a
    plain column here is enough. It's also the join key `Patient.family_doctor_practice_number`
    is compared against to derive whether a patient is registered with this physician (see
    app/patients/registration.py)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.PHYSICIAN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    practice_number: Mapped[str | None] = mapped_column(String(6), nullable=True)
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
    """A single identity per real person, unique by NAM across the whole app — not owned
    by any one physician. Holds administrative facts (vulnerability, the patient's family
    doctor and their practice number) that billing_codes needs but can never derive from a
    transcript (see CLAUDE.md). A physician's own relationship to a patient (an optional
    personal list + notes) lives separately in PhysicianPatient; whether a patient is
    *registered* with a given physician is derived, not stored here — see
    app/patients/registration.py, which compares `family_doctor_practice_number` against
    that physician's own `User.practice_number`."""

    __tablename__ = "patients"
    __table_args__ = (
        # Partial (not table-wide) so a soft-deleted patient never blocks re-adding the
        # same NAM, or a later correction of a duplicate. NULL ramq_number never
        # collides either way — both dialects already treat NULLs as distinct in a
        # unique index. Live on both dialects (unlike the FK ondelete/composite-FK
        # items) since SQLite enforces unique indexes unconditionally, no PRAGMA needed.
        Index(
            "ix_patients_ramq_number_active",
            "ramq_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    ramq_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender), nullable=True)
    is_vulnerable: Mapped[bool] = mapped_column(Boolean, default=False)
    family_doctor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    family_doctor_practice_number: Mapped[str | None] = mapped_column(String(6), nullable=True)
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


class PhysicianPatient(Base):
    """A physician's own, optional "my patients" list layered on top of the shared global
    Patient identity — membership plus a free-text personal note, nothing more.
    Deliberately does not carry a registration flag: whether a patient is registered with
    this physician is derived (see app/patients/registration.py), independent of whether
    the physician bothered to add them here. `ondelete="CASCADE"` on patient_id (unlike
    Claim's RESTRICT below) because this row is disposable per-physician metadata, not
    billing history — if the shared Patient identity is ever removed, every physician's
    roster annotation for them should disappear too."""

    __tablename__ = "physician_patients"
    __table_args__ = (UniqueConstraint("physician_id", "patient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Plain FK against the shared, global Patient identity — not scoped to this physician.
    # Any physician may bill any known patient regardless of "my patients list" membership
    # (that list is optional personal metadata, not a billing gate; see PhysicianPatient).
    # RESTRICT so a Patient can never be hard-deleted while any physician's claim still
    # references them — stricter than before, since it now protects every physician's
    # billing history, not just the one who happened to roster them.
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), index=True)
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
    # "high"/"medium"/"low" (see app/ramq_codes/models.py's ExtractedCode.confidence) —
    # String + boundary validation rather than a native Enum, same convention as
    # Claim.status just above: this vocabulary is controlled by the LLM prompt, not owned
    # by this codebase (see BACKLOG.md's item on the enum-strategy split).
    confidence: Mapped[str] = mapped_column(String(16))
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
