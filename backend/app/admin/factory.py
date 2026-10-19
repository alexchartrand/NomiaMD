"""Composition root for the admin console's services — built per request session, since
their repositories (and the audit trail) write in the caller's transaction."""

from app.admin.passwords import TemporaryPasswordGenerator
from app.admin.pricing import PriceTable
from app.admin.usage import UsageReport
from app.admin.users import UserAdminService
from app.audit import SessionAuditLog
from app.auth.factory import build_profile_service, password_hasher
from app.postgresdb import DbSession, LLMCallRepository, UserRepository


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
