"""The physician's dashboard: what's left to do, how billing is going, what came in last.
Orchestration only — each figure is computed by its own class (tasks.py, deadlines.py,
activity.py) from the inbox's rows, so statuses stay the inbox's derived ones. Read-only."""

from datetime import date, timedelta
from decimal import Decimal

from app.claims.mapper import ClaimMapper
from app.clock import Clock, clinic_day_bounds
from app.dashboard.activity import WeeklyActivity, clinic_day_of, week_start
from app.dashboard.deadlines import DeadlineWatch
from app.dashboard.models import DashboardOut, KpisOut
from app.dashboard.tasks import TaskCounter
from app.encounters.inbox import EncounterInbox
from app.postgresdb import BillRepository, ClaimDetail, ClaimRepository

RECENT_COUNT = 6


class DashboardService:
    def __init__(
        self,
        inbox: EncounterInbox,
        claims: ClaimRepository,
        bills: BillRepository,
        clock: Clock,
        deadlines: DeadlineWatch,
        activity: WeeklyActivity,
    ) -> None:
        self._inbox = inbox
        self._claims = claims
        self._bills = bills
        self._clock = clock
        self._deadlines = deadlines
        self._activity = activity

    async def for_physician(self, user_id: int) -> DashboardOut:
        today = self._clock.today()
        # Every encounter, like the inbox's "Tout": a note still to act on counts however old
        # it is — the oldest are the ones past RAMQ's deadline.
        rows = await self._inbox.period(user_id, None, None)
        drafts = await self._claims.list_unbilled(user_id)
        this_week = week_start(today)
        return DashboardOut(
            today=today,
            tasks=TaskCounter.count(rows),
            kpis=KpisOut(
                encounters_this_week=sum(1 for row in rows if week_start(clinic_day_of(row)) == this_week),
                draft_count=len(drafts),
                draft_total=_total(drafts),
                billed_this_month=await self._billed_in_month_of(user_id, today),
            ),
            deadlines=self._deadlines.items(rows, drafts, today),
            weekly_activity=self._activity.buckets(rows, today),
            recent_encounters=sorted(rows, key=lambda row: (row.received_at, row.id), reverse=True)[:RECENT_COUNT],
        )

    async def _billed_in_month_of(self, user_id: int, today: date) -> Decimal:
        first = today.replace(day=1)
        next_first = (first + timedelta(days=32)).replace(day=1)
        bills = await self._bills.list_generated_between(
            user_id, clinic_day_bounds(first)[0], clinic_day_bounds(next_first)[0]
        )
        return sum((bill.total_amount or Decimal(0) for bill in bills), Decimal(0))


def _total(drafts: list[ClaimDetail]) -> Decimal:
    totals = (ClaimMapper.total_amount(ClaimMapper.codes_out(draft.codes)) for draft in drafts)
    return sum((total for total in totals if total is not None), Decimal(0))
