"""Admin console request/response models. Mirrored by hand in frontend/src/api/admin.ts."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.admin.lockouts import Lockout
from app.admin.system import SystemReport
from app.admin.usage import UsageBucket, UsageGrouping, UsageReportResult
from app.admin.users import AdminAccount
from app.auth.profile import PracticeFacts
from app.postgresdb import (
    AuditEvent,
    ContactRequest,
    ContactRole,
    ContactTopic,
    FailedExtraction,
    PhysicianType,
    RemunerationType,
    UserRole,
)

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


class UsageBucketOut(BaseModel):
    key: str
    label: str
    calls: int
    input_tokens: int
    output_tokens: int
    # Estimated USD over the priced calls only; `unpriced_calls` were left out.
    cost_usd: Decimal
    unpriced_calls: int
    errors: int
    median_latency_ms: float | None
    p95_latency_ms: float | None

    @classmethod
    def from_bucket(cls, bucket: UsageBucket) -> "UsageBucketOut":
        return cls(
            key=bucket.key,
            label=bucket.label,
            calls=bucket.calls,
            input_tokens=bucket.input_tokens,
            output_tokens=bucket.output_tokens,
            cost_usd=round(bucket.cost, 4),
            unpriced_calls=bucket.unpriced_calls,
            errors=bucket.errors,
            median_latency_ms=bucket.median_latency_ms,
            p95_latency_ms=bucket.p95_latency_ms,
        )


class UsageReportOut(BaseModel):
    start: date
    end: date
    totals: UsageBucketOut
    extractions: int
    cost_per_extraction_usd: Decimal | None
    by_day: list[UsageBucketOut]
    group_by: UsageGrouping
    breakdown: list[UsageBucketOut]

    @classmethod
    def from_result(cls, result: UsageReportResult) -> "UsageReportOut":
        return cls(
            start=result.start,
            end=result.end,
            totals=UsageBucketOut.from_bucket(result.totals),
            extractions=result.extractions,
            cost_per_extraction_usd=(
                round(result.cost_per_extraction, 4) if result.cost_per_extraction is not None else None
            ),
            by_day=[UsageBucketOut.from_bucket(b) for b in result.by_day],
            group_by=result.grouping,
            breakdown=[UsageBucketOut.from_bucket(b) for b in result.breakdown],
        )


class DependencyCheckOut(BaseModel):
    ok: bool
    detail: str


class ModelConfigurationOut(BaseModel):
    chat_provider: str
    embedding_provider: str
    embedding_model: str | None
    step_models: dict[str, str]


class SystemReportOut(BaseModel):
    checked_at: datetime
    app_env: str
    app_version: str | None
    database: DependencyCheckOut
    codes_table: DependencyCheckOut
    models: ModelConfigurationOut
    row_counts: dict[str, int]
    failed_extractions: int
    encounters_past_purge: int

    @classmethod
    def from_report(cls, report: SystemReport) -> "SystemReportOut":
        return cls(
            checked_at=report.checked_at,
            app_env=report.app_env,
            app_version=report.app_version,
            database=DependencyCheckOut(ok=report.database.ok, detail=report.database.detail),
            codes_table=DependencyCheckOut(ok=report.codes_table.ok, detail=report.codes_table.detail),
            models=ModelConfigurationOut(
                chat_provider=report.models.chat_provider,
                embedding_provider=report.models.embedding_provider,
                embedding_model=report.models.embedding_model,
                step_models=report.models.step_models,
            ),
            row_counts=report.row_counts,
            failed_extractions=report.failed_extractions,
            encounters_past_purge=report.encounters_past_purge,
        )


class FailedExtractionOut(BaseModel):
    """Metadata only — the note text never leaves the inbox of the physician who owns it."""

    encounter_id: int
    user_id: int
    physician_name: str | None
    source_system: str
    service_date: date | None
    received_at: datetime
    error: str

    @classmethod
    def from_failure(cls, failure: FailedExtraction, names: dict[int, str]) -> "FailedExtractionOut":
        return cls(
            encounter_id=failure.encounter_id,
            user_id=failure.user_id,
            physician_name=names.get(failure.user_id),
            source_system=failure.source_system,
            service_date=failure.service_date,
            received_at=failure.received_at,
            error=failure.error,
        )


class LockoutOut(BaseModel):
    email: str
    failed_attempts: int
    last_attempt_at: datetime
    locked_until: datetime | None
    is_locked: bool
    known_account: bool

    @classmethod
    def from_lockout(cls, lockout: Lockout) -> "LockoutOut":
        return cls(
            email=lockout.email,
            failed_attempts=lockout.failed_attempts,
            last_attempt_at=lockout.last_attempt_at,
            locked_until=lockout.locked_until,
            is_locked=lockout.is_locked,
            known_account=lockout.known_account,
        )


class ContactRequestOut(BaseModel):
    id: int
    created_at: datetime
    name: str
    email: str
    phone: str | None
    organization: str | None
    role: ContactRole
    physician_count: int | None
    topic: ContactTopic
    plan: str | None
    message: str | None

    @classmethod
    def from_row(cls, row: ContactRequest) -> "ContactRequestOut":
        return cls(
            id=row.id,
            created_at=row.created_at,
            name=row.name,
            email=row.email,
            phone=row.phone,
            organization=row.organization,
            role=row.role,
            physician_count=row.physician_count,
            topic=row.topic,
            plan=row.plan,
            message=row.message,
        )


class AuditEventOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    actor_id: int | None
    actor_name: str | None
    target_user_id: int | None
    target_name: str | None
    details: dict | None
    ip: str | None

    @classmethod
    def from_event(cls, event: AuditEvent, names: dict[int, str]) -> "AuditEventOut":
        return cls(
            id=event.id,
            created_at=event.created_at,
            action=event.action,
            actor_id=event.actor_id,
            actor_name=names.get(event.actor_id) if event.actor_id is not None else None,
            target_user_id=event.target_user_id,
            target_name=names.get(event.target_user_id) if event.target_user_id is not None else None,
            details=event.details,
            ip=event.ip,
        )
