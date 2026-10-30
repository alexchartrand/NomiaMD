"""`/admin/*` — the admin console's API. Every route requires an active admin (require_admin
at the router level); routes that act on an account also take the admin as `actor` for the
audit trail."""

from collections.abc import Awaitable
from datetime import date, datetime, timedelta
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.admin.extractions import EncounterNotRetryableError, FailedExtractions
from app.admin.factory import (
    get_audit_events,
    get_contact_requests,
    get_failed_extractions,
    get_lockout_service,
    get_system_status,
    get_usage_report,
    get_user_admin_service,
    get_user_repository,
)
from app.admin.lockouts import LockoutService
from app.admin.models import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    AuditEventOut,
    ContactRequestOut,
    FailedExtractionOut,
    LockoutOut,
    SystemReportOut,
    TemporaryPasswordOut,
    UsageReportOut,
)
from app.admin.system import SystemStatus
from app.admin.usage import UsageGrouping, UsageReport
from app.admin.users import (
    AccountChanges,
    AdminGuardError,
    IssuedPassword,
    NewAccount,
    UserAdminService,
    UserNotFoundError,
)
from app.auth import require_admin
from app.clock import Clock, get_clock
from app.encounters.factory import get_extraction_queue
from app.intake.queue import ExtractionQueue
from app.postgresdb import (
    AuditEventFilter,
    AuditEventRepository,
    ContactRequestRepository,
    DuplicateEmailError,
    DuplicatePracticeNumberError,
    User,
    UserRepository,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

T = TypeVar("T")


async def _account_errors_as_http(call: Awaitable[T]) -> T:
    """Maps the user-admin service's domain errors onto HTTP answers, in one place."""
    try:
        return await call
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable") from exc
    except AdminGuardError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec ce courriel."
        ) from exc
    except DuplicatePracticeNumberError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce numéro de pratique est déjà associé à un autre compte.",
        ) from exc


def _issued(issued: IssuedPassword) -> TemporaryPasswordOut:
    return TemporaryPasswordOut(
        user=AdminUserOut.from_admin_account(issued.account), temporary_password=issued.temporary_password
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(service: UserAdminService = Depends(get_user_admin_service)) -> list[AdminUserOut]:
    return [AdminUserOut.from_admin_account(a) for a in await service.list_accounts()]


@router.post("/users", response_model=TemporaryPasswordOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    actor: User = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> TemporaryPasswordOut:
    new = NewAccount(
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        practice_number=body.practice_number,
        facts=body.practice_facts() if body.has_practice_facts() else None,
    )
    return _issued(await _account_errors_as_http(service.create(actor, new)))


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: int,
    body: AdminUserUpdate,
    actor: User = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> AdminUserOut:
    changes = AccountChanges(
        full_name=body.full_name, role=body.role, practice_number=body.practice_number, facts=body.practice_facts()
    )
    return AdminUserOut.from_admin_account(await _account_errors_as_http(service.update(actor, user_id, changes)))


@router.post("/users/{user_id}/deactivate", response_model=AdminUserOut)
async def deactivate_user(
    user_id: int,
    actor: User = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> AdminUserOut:
    return AdminUserOut.from_admin_account(await _account_errors_as_http(service.deactivate(actor, user_id)))


@router.post("/users/{user_id}/reactivate", response_model=AdminUserOut)
async def reactivate_user(
    user_id: int,
    actor: User = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> AdminUserOut:
    return AdminUserOut.from_admin_account(await _account_errors_as_http(service.reactivate(actor, user_id)))


@router.post("/users/{user_id}/reset-password", response_model=TemporaryPasswordOut)
async def reset_user_password(
    user_id: int,
    actor: User = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> TemporaryPasswordOut:
    return _issued(await _account_errors_as_http(service.reset_password(actor, user_id)))


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_sessions(
    user_id: int,
    actor: User = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> None:
    await _account_errors_as_http(service.revoke_sessions(actor, user_id))


# A year at most: the report folds the range's raw rows in memory (app/admin/usage.py).
_MAX_USAGE_DAYS = 366


@router.get("/usage", response_model=UsageReportOut)
async def usage_report(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    group_by: UsageGrouping = Query(default=UsageGrouping.MODEL),
    report: UsageReport = Depends(get_usage_report),
    clock: Clock = Depends(get_clock),
) -> UsageReportOut:
    """Clinic days, both included. Default: the last 30 days, today included."""
    end = end or clock.today()
    start = start or end - timedelta(days=29)
    if start > end or (end - start).days >= _MAX_USAGE_DAYS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Période invalide")
    return UsageReportOut.from_result(await report.build(start, end, group_by))


@router.get("/system", response_model=SystemReportOut)
async def system_report(status_: SystemStatus = Depends(get_system_status)) -> SystemReportOut:
    return SystemReportOut.from_report(await status_.report())


@router.get("/extraction-failures", response_model=list[FailedExtractionOut])
async def list_extraction_failures(
    limit: int = Query(default=100, ge=1, le=200),
    failures: FailedExtractions = Depends(get_failed_extractions),
) -> list[FailedExtractionOut]:
    listed = await failures.list(limit=limit)
    return [FailedExtractionOut.from_failure(f, listed.physician_names) for f in listed.failures]


@router.post("/encounters/{encounter_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_extraction(
    encounter_id: int,
    actor: User = Depends(require_admin),
    failures: FailedExtractions = Depends(get_failed_extractions),
    queue: ExtractionQueue = Depends(get_extraction_queue),
) -> None:
    try:
        await failures.retry(actor, encounter_id, queue)
    except EncounterNotRetryableError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rencontre introuvable ou sans patient") from exc


@router.get("/lockouts", response_model=list[LockoutOut])
async def list_lockouts(lockouts: LockoutService = Depends(get_lockout_service)) -> list[LockoutOut]:
    return [LockoutOut.from_lockout(lockout) for lockout in await lockouts.list()]


@router.delete("/lockouts/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_login(
    email: str,
    actor: User = Depends(require_admin),
    lockouts: LockoutService = Depends(get_lockout_service),
) -> None:
    await lockouts.unlock(actor, email)


@router.get("/contact-requests", response_model=list[ContactRequestOut])
async def list_contact_requests(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    requests: ContactRequestRepository = Depends(get_contact_requests),
) -> list[ContactRequestOut]:
    return [ContactRequestOut.from_row(row) for row in await requests.list(limit=limit, offset=offset)]


@router.get("/audit", response_model=list[AuditEventOut])
async def list_audit_events(
    action: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    events: AuditEventRepository = Depends(get_audit_events),
    users: UserRepository = Depends(get_user_repository),
) -> list[AuditEventOut]:
    rows = await events.list(
        AuditEventFilter(action=action, user_id=user_id, since=since, until=until), limit=limit, offset=offset
    )
    names = {u.id: u.full_name for u in await users.list_all()}
    return [AuditEventOut.from_event(row, names) for row in rows]
