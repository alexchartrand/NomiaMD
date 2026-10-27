"""Composition root for the work site and shift services, over the request's single session."""

from app.postgresdb import DbSession, ShiftRepository, WorkSiteRepository
from app.shifts.service import ShiftService, WorkSiteService


def get_work_site_service(session: DbSession) -> WorkSiteService:
    return WorkSiteService(WorkSiteRepository(session))


def get_shift_service(session: DbSession) -> ShiftService:
    return ShiftService(ShiftRepository(session), WorkSiteRepository(session))
