"""ORM shapes only — persistence lives in repositories/, not here.

There is no Alembic: the schema is created by `create_all` (database.py) and a local or demo
DB is simply deleted and recreated when it changes. That holds until the first real release —
adopt migrations before then (see BACKLOG.md)."""

import enum
from datetime import date, datetime, time
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
    Time,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.postgresdb.database import Base

# JSON on SQLite (dev), JSONB on Postgres: keeps the retention scrub and "which extractions
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
    number of accounts may leave it blank.

    `session_version` is stamped into every session token (app/auth/security.py); bumping it
    revokes all of the account's open sessions at once — on deactivation, an admin password
    reset, a role change or an explicit "log out everywhere". `must_change_password` is set
    on an account an admin created or reset with a temporary password: until the user picks
    their own, every route but the password change refuses them (app/auth/dependencies.py)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.PHYSICIAN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    practice_number: Mapped[str | None] = mapped_column(String(6), nullable=True, unique=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class LoginThrottle(Base):
    """Failed-login bookkeeping per login email (app/auth/throttle.py), not per `users` row:
    an unknown email is throttled exactly like a real one, so a lockout never reveals which
    accounts exist. `email` is stored lowercased and stripped, so case variants share a
    counter. `failed_attempts` counts every attempt since the last success (each is counted
    before its password is checked); the row is deleted on a successful login."""

    __tablename__ = "login_throttles"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(CreatedAtMixin, Base):
    """Append-only trail of account-level events: what an admin did to which account, and
    every login on a real account (app/audit/). Never updated or deleted by the app.

    `action` is a plain String (app/audit/actions.py's AuditAction values), not a native
    Enum, so a new action needs no schema change. `details` carries what changed (field
    names, old → new role) — never a password, a token or patient data. Login attempts on
    unknown emails aren't recorded, so guessing addresses can't grow this table."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    details: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


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


class WorkSite(TimestampMixin, Base):
    """A place a physician works — "Urgence Hôpital X", "GMF Y" — and the care setting
    (app/care_setting.py) billing reads from it. The physician's own list, picked from when
    adding a shift.

    Never hard-deleted: deactivating hides it from new shifts, while the shifts already on it
    keep their own snapshot of its care setting (see Shift)."""

    __tablename__ = "work_sites"
    __table_args__ = (
        # String + CHECK rather than a native Enum, same as encounters.channel.
        CheckConstraint(
            "care_setting IN ('cabinet', 'gmf', 'domicile', 'urgence', 'hospitalisation', 'chsld')",
            name="ck_work_sites_care_setting",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    care_setting: Mapped[str] = mapped_column(String(32))
    # RAMQ's établissement number, when the site is one — direct submission will need it.
    etablissement_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShiftSeries(CreatedAtMixin, Base):
    """Groups the shifts saved together over a date range (two weeks at a clinic, a week on
    call), so the physician can edit or remove them as one. Only an identity: each shift
    keeps its own date, hours and site."""

    __tablename__ = "shift_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Shift(TimestampMixin, Base):
    """One block of work at a site — an ER evening, a CHSLD morning — in the clinic's local
    time (America/Montreal), the way RAMQ states its hours: a date and a start and end time,
    the end at or before the start meaning the next day (a night shift 23:00–07:00). Local
    times rather than instants also keep it off SQLite's tz-naive DateTime.

    `care_setting` is copied from the site when the shift is saved, so editing or deactivating
    a site never changes what past shifts were billed under. `period` is the physician's pick
    (jour/soir/nuit — app/shifts/periods.py), not derived from the hours.

    `series_id` links the shifts saved together over a date range (ShiftSeries); null for a
    shift saved on its own.

    Never hard-deleted: removing a shift sets `voided_at`."""

    __tablename__ = "shifts"
    __table_args__ = (
        # The calendar's "my shifts between these dates". id breaks ties for same-day shifts.
        Index("ix_shifts_user_service_date", "user_id", "service_date", "id"),
        CheckConstraint(
            "care_setting IN ('cabinet', 'gmf', 'domicile', 'urgence', 'hospitalisation', 'chsld')",
            name="ck_shifts_care_setting",
        ),
        CheckConstraint("period IN ('jour', 'soir', 'nuit')", name="ck_shifts_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    work_site_id: Mapped[int] = mapped_column(ForeignKey("work_sites.id", ondelete="RESTRICT"), index=True)
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("shift_series.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    care_setting: Mapped[str] = mapped_column(String(32))
    period: Mapped[str] = mapped_column(String(8))
    # The day the shift starts on, in the clinic's calendar.
    service_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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

    The target of the retention scrub (app/retention/): the note text lives here and nowhere
    else. Past retention, `note_text` is set to NULL (with the run results' clinical text,
    app/retention/note_scrub.py) and `note_scrubbed_at` records when; the row itself, its
    runs' codes and its claims stay, so billing history and RAMQ follow-ups outlive the note.
    When that happens is derived (EncounterRepository.list_due_for_scrub), never stored: it
    moves whenever a claim is billed again. Re-importing the same note restores its text
    (`note_restored_at`). Deleting an encounter (only an unclaimed one, from the inbox)
    cascades to its runs and their results.

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
    # NULL once scrubbed (note_scrubbed_at says when).
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    note_scrubbed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When a re-import brought the scrubbed text back; retention counts again from here.
    note_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The shift the physician said this encounter belongs to (picked at paste/upload or on the
    # encounter). Null means "not stated": the shift is then derived from the encounter's date
    # and time (app/shifts/matching.py), never stored.
    shift_id: Mapped[int | None] = mapped_column(
        ForeignKey("shifts.id", ondelete="RESTRICT"), nullable=True, index=True
    )


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
    # Where and when the run took the encounter to be (app/shifts/encounter_setting.py), as
    # it was then: the shift or care setting can change afterwards, and the codes were chosen
    # under these. Each null when unknown.
    care_setting: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id", ondelete="RESTRICT"), nullable=True)
    shift_period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    day_type: Mapped[str | None] = mapped_column(String(16), nullable=True)


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


class LLMCall(CreatedAtMixin, Base):
    """One metered chat or embedding call (app/llm/usage.py's LLMCallRecord), kept for the
    admin console's usage and cost report. Stored with what it was for: the physician, and
    for an extraction its encounter and run (both SET NULL, so the retention purge of an
    encounter never has to wait on its usage rows — the counts outlive the note)."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_started_at", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_runs.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Numeric(12, 1))
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
    """One physician-confirmed RAMQ claim for an encounter — or, billed by hand without one,
    for a patient on a date — with many code lines (ClaimCode).

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
    # they outlive the note's retention scrub, so a claim still says which exact note version
    # it was billed from.
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_note_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_note_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SET NULL so deleting an encounter (see Encounter) never fails on a voided claim. Never set on a
    # claim billed without an encounter (source_system "manual" — app/claims/manual.py).
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
        # A NULL confidence passes (a code the physician added by hand was never scored).
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="ck_claim_codes_confidence"),
        CheckConstraint("origin IN ('suggested', 'manual')", name="ck_claim_codes_origin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    # Where the line came from: "suggested" — offered by the claim's extraction run, snapshot
    # from its stored result; "manual" — added by the physician from the code search, snapshot
    # from the current codes table (app/claims/catalog.py). Stored rather than derived: the
    # run it would be derived from may be purged, and the codes table is regenerated.
    origin: Mapped[str] = mapped_column(String(16), default="suggested", server_default="suggested")
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
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


class ShiftClaim(TimestampMixin, Base):
    """A claim for a shift's own codes (09791, 19953 — app/shift_claims/), billed for the hours
    worked rather than for a patient: no patient, no NAM. Its code lines are ShiftClaimCode.

    The shift's site, care setting and hours are snapshotted at save time, like a Claim's
    billing context: editing the shift or its site later never reinterprets what was claimed.

    Status is derived like a Claim's (app/claims/status.py): "soumis" exactly when on a bill.
    Never hard-deleted: removing a draft sets `voided_at`."""

    __tablename__ = "shift_claims"
    __table_args__ = (
        Index("ix_shift_claims_physician_service_date", "physician_id", "service_date"),
        CheckConstraint(
            "garde_option IN ('acte', 'premier', 'second', 'partage')", name="ck_shift_claims_garde_option"
        ),
        # One live claim per shift. Partial so voiding a draft frees its shift to be claimed again.
        Index(
            "ix_shift_claims_shift_active",
            "shift_id",
            unique=True,
            postgresql_where=text("voided_at IS NULL"),
            sqlite_where=text("voided_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    physician_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="RESTRICT"))
    service_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    care_setting: Mapped[str] = mapped_column(String(32))
    period: Mapped[str] = mapped_column(String(8))
    work_site_name: Mapped[str] = mapped_column(String(120))
    etablissement_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The physician's choice for the garde (app/shift_claims/catalog/garde.py): à l'acte, or a
    # P.G. 1.4 forfait — and then the period's patient services are paid at 101 % or 53,2 %.
    garde_option: Mapped[str] = mapped_column(String(16), default="acte", server_default="acte")
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id", ondelete="SET NULL"), nullable=True, index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShiftClaimCode(CreatedAtMixin, Base):
    """One shift code on a shift claim, for a number of hours. Description and fees are
    snapshotted from the curated catalog at save time, like ClaimCode's from the codes table."""

    __tablename__ = "shift_claim_codes"
    __table_args__ = (
        UniqueConstraint("shift_claim_id", "code", name="uq_shift_claim_codes_claim_code"),
        CheckConstraint("origin IN ('suggested', 'manual')", name="ck_shift_claim_codes_origin"),
        CheckConstraint("hours > 0", name="ck_shift_claim_codes_hours"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_claim_id: Mapped[int] = mapped_column(ForeignKey("shift_claims.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    # "suggested" — the shift's rules earned it (app/shift_claims/rules.py); "manual" — the
    # physician added a code the rules didn't suggest (an établissement's own holiday, say).
    origin: Mapped[str] = mapped_column(String(16))
    hours: Mapped[int] = mapped_column(Integer)
    # Null when the catalog stated no fee on the shift's date.
    hourly_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # The RAMQ secteur de dispensation the code is billed under ("07") and its name.
    secteur_dispensation: Mapped[str] = mapped_column(String(2))
    secteur_dispensation_label: Mapped[str] = mapped_column(Text)
    # Where the catalog says the code is stated in the manual, e.g. "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)".
    source: Mapped[str] = mapped_column(Text)


class ContactRole(str, enum.Enum):
    PHYSICIAN = "medecin"
    CLINIC_MANAGER = "gestionnaire"
    PARTNER = "partenaire"
    OTHER = "autre"


class ContactTopic(str, enum.Enum):
    DEMO = "demo"
    TRIAL = "essai"
    PRICING = "tarifs"
    PARTNERSHIP = "partenariat"
    OTHER = "autre"


class ContactRequest(CreatedAtMixin, Base):
    """A message sent from the public site's contact form (POST /contact) — a prospect, not a
    user, so no foreign key to anything. Submitting the form requires ticking the Law 25
    consent box; `consent_at` records when that happened (always the row's own creation
    time today, kept separate so a later consent-withdrawal flow has somewhere to write)."""

    __tablename__ = "contact_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[ContactRole] = mapped_column(Enum(ContactRole))
    physician_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    topic: Mapped[ContactTopic] = mapped_column(Enum(ContactTopic))
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
