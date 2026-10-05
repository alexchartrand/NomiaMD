"""Composition root for DashboardService — wires the inbox and repositories over the
request's single session, and the clinic clock (overridden in tests to pin "today")."""

from fastapi import Depends

from app.clock import Clock, get_clock
from app.dashboard.activity import WeeklyActivity
from app.dashboard.deadline import BillingDeadline
from app.dashboard.deadlines import DeadlineWatch
from app.dashboard.service import DashboardService
from app.encounters.inbox import EncounterInbox
from app.postgresdb import BillRepository, ClaimRepository, DbSession


def get_dashboard_service(session: DbSession, clock: Clock = Depends(get_clock)) -> DashboardService:
    return DashboardService(
        EncounterInbox(session),
        ClaimRepository(session),
        BillRepository(session),
        clock,
        DeadlineWatch(BillingDeadline()),
        WeeklyActivity(),
    )
