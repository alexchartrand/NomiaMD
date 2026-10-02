"""ORM shapes only — persistence lives in repositories/, not here.

There is no Alembic: the schema is created by `create_all` (database.py) and a local or demo
DB is simply deleted and recreated when it changes. That holds until the first real release —
adopt migrations before then (see BACKLOG.md)."""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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

# JSON on SQLite (dev), JSONB on Postgres: keeps the retention purge and "which extractions
# mention this NAM" query indexable instead of a full-table LIKE.
_JSON = JSON().with_variant(JSONB, "postgresql")


class CreatedAtMixin:
    """Stamped by the database, never by Python — one clock (the DB's) for every row, and
    no `default=` + `server_default=` pair to keep in sync. Base's `eager_defaults` reads the
    value back on INSERT, so it's populated right after a flush without a refresh."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PHYSICIAN = "physician"


class PhysicianType(str, enum.Enum):
    """Placeholder list — refine once the exact set of practice settings is confirmed.

    Stored as its code (a plain String column validated at the API boundary), not a native
    Enum: RAMQ controls this vocabulary, not this codebase. The French label is display
    only and never reaches the database."""

    MED_FAM = "med_fam"
    SPECIALISTE = "specialiste"
    AUTRE = "autre"

    @property
    def label(self) -> str:
        return _PHYSICIAN_TYPE_LABELS[self]


_PHYSICIAN_TYPE_LABELS = {
    PhysicianType.MED_FAM: "Médecin de famille",
    PhysicianType.SPECIALISTE: "Spécialiste",
    PhysicianType.AUTRE: "Autre",
}


class RemunerationType(str, enum.Enum):
    """Same storage convention as PhysicianType."""

    MIXTE = "mixte"
    A_L_ACTE = "a_l_acte"

    @property
    def label(self) -> str:
        return _REMUNERATION_TYPE_LABELS[self]


_REMUNERATION_TYPE_LABELS = {
    RemunerationType.MIXTE: "Mixte",
    RemunerationType.A_L_ACTE: "À l'acte",
}


class User(CreatedAtMixin, Base):
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
    app/patients/registration.py) — hence unique: two accounts sharing one would make that
    derivation ambiguous. NULLs never collide in a unique index on either dialect, so any
    number of accounts may leave it blank."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.PHYSICIAN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    practice_number: Mapped[str | None] = mapped_column(String(6), nullable=True, unique=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhysicianProfile(TimestampMixin, Base):
    """A physician's practice facts, as of a date — append-only, one row per edit rather
    than one row per physician.

    These aren't user preferences: `remuneration_type` (mixte vs à l'acte),
    `physician_type` and `panel_size` are administrative facts that decide which RAMQ codes
    a physician may legally bill, and they change over a career. Keeping them as mutable
    columns on `users` meant editing the profile silently rewrote the basis of every past
    claim — the same failure ClaimCode's fee snapshot exists to prevent. A claim must stay
    interpretable under the values in effect on its own service_date, so read it with
    `get_effective_on(user_id, service_date)`, not `get_current`.

    One version per (user, effective_from): a same-day edit is a correction, not a second
    version of reality, and PhysicianProfileRepository.upsert overwrites it with ON CONFLICT
    rather than a select-then-insert that two concurrent saves could both pass.

    New editable fields are added here as nullable columns; `users` doesn't grow.
    """

    __tablename__ = "physician_profiles"
    # Also the index for every (user_id, date) lookup — no separate user_id index needed.
    __table_args__ = (UniqueConstraint("user_id", "effective_from", name="uq_physician_profiles_user_effective"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    effective_from: Mapped[date] = mapped_column(Date)
    # PhysicianType / RemunerationType codes, validated at the API boundary.
    physician_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    panel_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remuneration_type: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Gender(str, enum.Enum):
    """Placeholder list — refine once the exact set needed is confirmed."""

    MALE = "M"
    FEMALE = "F"
    OTHER = "X"


class Patient(TimestampMixin, Base):
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
        # unique index. Only as strong as the NAM's canonical form: PatientBase
        # (app/patients/models.py) normalizes it, and the CHECKs below refuse anything else.
        Index(
            "ix_patients_ramq_number_active",
            "ramq_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        # Canonical NAM: 4 uppercase letters + 8 digits. Same rule, each dialect's syntax —
        # SQLite has no regex operator by default, but GLOB's character classes suffice.
        CheckConstraint(
            "ramq_number ~ '^[A-Z]{4}[0-9]{8}$'", name="ck_patients_ramq_number_canonical"
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "ramq_number GLOB '[A-Z][A-Z][A-Z][A-Z][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'",
            name="ck_patients_ramq_number_canonical_sqlite",
        ).ddl_if(dialect="sqlite"),
        # Name search is a substring ILIKE (PatientRepository.search), which a btree can't
        # serve; a trigram GIN index can. Postgres only — needs the pg_trgm extension,
        # which PostgresDB.open() creates. SQLite dev DBs are small enough to scan.
        Index(
            "ix_patients_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    ramq_number: Mapped[str | None] = mapped_column(String(12), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender), nullable=True)
    is_vulnerable: Mapped[bool] = mapped_column(Boolean, default=False)
    family_doctor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    family_doctor_practice_number: Mapped[str | None] = mapped_column(String(6), nullable=True)
    # Nullable timestamp rather than a bool: under Law 25 the deletion date is the thing
    # an audit asks for, not just whether the patient is gone.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class PhysicianPatient(TimestampMixin, Base):
    """A physician's own, optional "my patients" list layered on top of the shared global
    Patient identity — membership plus a free-text personal note, nothing more.
    Deliberately does not carry a registration flag: whether a patient is registered with
    this physician is derived (see app/patients/registration.py), independent of whether
    the physician bothered to add them here. `ondelete="CASCADE"` on patient_id (unlike
    Claim's RESTRICT below) because this row is disposable per-physician metadata, not
    billing history — if the shared Patient identity is ever removed, every physician's
    roster annotation for them should disappear too."""

    __tablename__ = "physician_patients"
    # The unique constraint's (physician_id, patient_id) index serves physician_id lookups.
    __table_args__ = (UniqueConstraint("physician_id", "patient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Encounter(TimestampMixin, Base):
    """One signed clinical note from one source — the unit the physician works on. A note
    arrives (pasted, pushed by the extension or a scribe, pulled from a DMÉ), gets a patient,
    is extracted (ExtractionRun, possibly several times) and is reviewed into a claim.

    The single target of the retention purge: the note text lives here and nowhere else.
    Deleting an encounter cascades to its runs and their results, and detaches any claim
    made from them (SET NULL — claims already snapshot what they need, including the note's
    hash and external id). `purge_after` is when that may happen; nothing sets or acts on it
    yet, since the retention period itself isn't decided.

    There is no stored status — see app/intake/status.py. `extraction_error` is stored only
    because a failed extraction leaves no other trace to derive it from.

    An amended note is a new row, not an update: the old version points at it through
    `superseded_by_id`, so a claim made from the old version keeps the exact text it was
    billed from."""

    __tablename__ = "encounters"
    __table_args__ = (
        # One row per version of an external note. Partial so pasted notes (no external id)
        # are never deduplicated here; a changed note has a new hash and is a new version.
        Index(
            "ix_encounters_external_version",
            "user_id",
            "source_system",
            "external_note_id",
            "content_hash",
            unique=True,
            postgresql_where=text("external_note_id IS NOT NULL"),
            sqlite_where=text("external_note_id IS NOT NULL"),
        ),
        # The inbox's "my encounters on this day". id breaks ties: created_at comes from the
        # DB clock, which SQLite only keeps to the second. Also serves user_id-only lookups.
        Index("ix_encounters_user_service_date", "user_id", "service_date", "id"),
        # String + CHECK rather than a native Enum, same as claim_codes.confidence: new
        # channels are added as connectors land, without a type migration on Postgres.
        CheckConstraint(
            "channel IN ('paste', 'upload', 'extension', 'scribe_webhook', 'fhir_pull', 'partner_api', 'sample')",
            name="ck_encounters_channel",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Null until the note is matched to a patient ("à associer"). RESTRICT, same as Claim.
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_system: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    external_note_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_encounter_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # sha256 hex of note_text — see app/intake/hashing.py.
    content_hash: Mapped[str] = mapped_column(String(64))
    service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Source-specific facts that don't drive any query: start/end times, location,
    # établissement...
    encounter_meta: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    note_text: Mapped[str] = mapped_column(Text)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The physician's answers to a "doublon possible" flag (the flag itself is derived — see
    # app/encounters/duplicates.py). Confirmed: this one is the same visit as
    # `duplicate_of_id`, hidden from the inbox and never billed. Dismissed: it's a distinct
    # visit, and isn't flagged again.
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ExtractionRun(CreatedAtMixin, Base):
    """One extraction of an encounter's note: who ran it, for which patient, and (through
    ExtractionRunResult) each stage's output. The note text itself stays on the Encounter.
    The physician picks the patient *before* extraction runs, and every code it suggests
    was eligibility-filtered for that patient — so a claim takes its patient from here
    (Claim.extraction_run_id), never from its own request body.

    Deleted with its encounter (CASCADE), which cascades to its ExtractionRunResult rows and
    detaches any claim made from it (SET NULL)."""

    __tablename__ = "extraction_runs"
    __table_args__ = (Index("ix_extraction_runs_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), index=True)


class ExtractionRunResult(CreatedAtMixin, Base):
    """One pipeline stage's output within a run (consultation_summary, billing_codes, ...).
    Per-stage LLM usage (tokens, latency) belongs here too once that's logged — see
    BACKLOG.md's LLM usage item."""

    __tablename__ = "extraction_results"
    __table_args__ = (UniqueConstraint("run_id", "task", name="uq_extraction_results_run_task"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("extraction_runs.id", ondelete="CASCADE"))
    task: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(_JSON)


class Bill(Base):
    """One generated invoice grouping many claims over a date range. The PDF is
    rendered on demand from the linked claims (Claim.bill_id — themselves already snapshots,
    see ClaimCode), so nothing is stored as bytes; total_amount/claim_count are snapshotted
    anyway so listing bills never has to re-sum every claim's codes.

    Never hard-deleted: "deleting" a bill sets `voided_at` and releases its claims back to
    draft (BillService.delete), so the invoice number and its totals stay on record."""

    __tablename__ = "bills"
    # Also serves physician_id-only lookups — no separate physician_id index needed.
    __table_args__ = (Index("ix_bills_physician_start_date", "physician_id", "start_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    claim_count: Mapped[int] = mapped_column(Integer)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Claim(TimestampMixin, Base):
    """One physician-confirmed RAMQ claim for an encounter, with many code lines
    (ClaimCode).

    There is no stored status: a claim is "soumis" exactly when it's on a bill (`bill_id IS
    NOT NULL`) and "brouillon" otherwise — see app/claims/status.py. A stored copy could only
    ever drift from the link it describes.

    Never hard-deleted: "deleting" a draft sets `voided_at`, so a claim that was ever on a
    bill can't be erased by voiding the bill and then the claim."""

    __tablename__ = "claims"
    __table_args__ = (
        # Also serves physician_id-only lookups — no separate physician_id index needed.
        Index("ix_claims_physician_service_date", "physician_id", "service_date"),
        # One live claim per extraction run. Partial so voiding a claim frees its run to be
        # claimed again, same as a hard delete used to.
        Index(
            "ix_claims_extraction_run_active",
            "extraction_run_id",
            unique=True,
            postgresql_where=text("voided_at IS NULL"),
            sqlite_where=text("voided_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Copied from the extraction run the claim was made from, never from the request. Plain
    # FK against the shared, global Patient identity — any physician may bill any known
    # patient. RESTRICT so a Patient can never be hard-deleted while any claim references them.
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), index=True)
    service_date: Mapped[date] = mapped_column(Date)
    # Snapshotted from the run's encounter at save time, like the billing context below:
    # they outlive the encounter's purge, so a claim still says which exact note version
    # it was billed from.
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_note_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_note_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SET NULL so the retention purge (see Encounter) never fails on a claim.
    extraction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="SET NULL"), nullable=True
    )
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id", ondelete="SET NULL"), nullable=True, index=True)

    # The billing context the codes were chosen under, snapshotted at save time for the
    # same reason as ClaimCode's fees: the patient's registration/vulnerability and the
    # physician's panel size change later, and re-deriving them would silently reinterpret
    # a past claim. Null means "unknown at save time", never "false".
    is_registered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_vulnerable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    patient_age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    panel_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClaimCode(CreatedAtMixin, Base):
    """One selected RAMQ code on a claim. Fields are a snapshot of the candidate and the
    fee the physician picked at save time (not a live join back to the LanceDB codes table),
    because that table is a regenerated external artifact — re-deriving a historical claim's
    fee/rules would silently rewrite history whenever the tariff data changes."""

    __tablename__ = "claim_codes"
    __table_args__ = (
        # Also the index for claim_id lookups.
        UniqueConstraint("claim_id", "code", name="uq_claim_codes_claim_code"),
        # String + CHECK rather than a native Enum: the LLM prompt controls this
        # vocabulary, not this codebase (see app/ramq_codes/models.py's ExtractedCode).
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="ck_claim_codes_confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text)
    # Dollars only. A fee in units (anesthesia base units) is never a price: its count goes
    # in fee_units and fee_amount stays NULL — see app/claims/fees.py.
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fee_units: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # The manual's raw role column (R = 1, R = 2, R = 7…), meaning is section-specific.
    fee_role: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_lieux: Mapped[list[str] | None] = mapped_column(_JSON, nullable=True)
    majoration: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The RAMQ manual revision the candidate came from — not carried by extraction results
    # yet (see BACKLOG.md's manual_rev item), so NULL until it is.
    manual_rev: Mapped[str | None] = mapped_column(String(32), nullable=True)
