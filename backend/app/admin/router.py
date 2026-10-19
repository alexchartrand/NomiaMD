"""`/admin/*` — the admin console's API. Every route requires an active admin (require_admin
at the router level); routes that act on an account also take the admin as `actor` for the
audit trail."""

from collections.abc import Awaitable
from datetime import date, timedelta
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.admin.factory import get_usage_report, get_user_admin_service
from app.admin.models import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    TemporaryPasswordOut,
    UsageReportOut,
)
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
from app.postgresdb import DuplicateEmailError, DuplicatePracticeNumberError, User

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


# A year at most: the report folds the range's rows in memory (app/admin/usage.py).
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
