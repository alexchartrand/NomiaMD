"""Composition root for the admin console's services — built per request session, since
their repositories (and the audit trail) write in the caller's transaction."""

from fastapi import Depends

from app.admin.extractions import FailedExtractions
from app.admin.lockouts import LockoutService
from app.admin.passwords import TemporaryPasswordGenerator
from app.admin.pricing import PriceTable
from app.admin.system import SystemStatus
from app.admin.usage import UsageReport
from app.admin.users import UserAdminService
from app.audit import SessionAuditLog
from app.auth.factory import build_profile_service, password_hasher
from app.clock import Clock, get_clock
from app.code_catalog.registry import get_code_catalog_repository
from app.postgresdb import (
    AuditEventRepository,
    ContactRequestRepository,
    DbSession,
    EncounterRepository,
    LLMCallRepository,
    LoginThrottleRepository,
    TableStatsRepository,
    UserRepository,
)
from app.retention import RetentionPolicy


def get_user_admin_service(session: DbSession) -> UserAdminService:
    return UserAdminService(
        user_repository=UserRepository(session),
        profile_service=build_profile_service(session),
        password_hasher=password_hasher(),
        password_generator=TemporaryPasswordGenerator(),
        audit_log=SessionAuditLog(session),
    )


def get_usage_report(session: DbSession) -> UsageReport:
    return UsageReport(LLMCallRepository(session), UserRepository(session), PriceTable.from_settings())


def get_system_status(session: DbSession, clock: Clock = Depends(get_clock)) -> SystemStatus:
    try:
        codes = get_code_catalog_repository()
    except RuntimeError:
        codes = None
    return SystemStatus(
        TableStatsRepository(session),
        EncounterRepository(session),
        codes,
        RetentionPolicy.from_settings(),
        clock,
    )


def get_lockout_service(session: DbSession) -> LockoutService:
    return LockoutService(LoginThrottleRepository(session), UserRepository(session), SessionAuditLog(session))


def get_failed_extractions(session: DbSession) -> FailedExtractions:
    return FailedExtractions(EncounterRepository(session), UserRepository(session), SessionAuditLog(session))


def get_audit_events(session: DbSession) -> AuditEventRepository:
    return AuditEventRepository(session)


def get_contact_requests(session: DbSession) -> ContactRequestRepository:
    return ContactRequestRepository(session)


def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)
