"""The physician's dashboard: what's left to do, how billing is going, what came in last.
Orchestration only — each figure is computed by its own class (tasks.py, deadlines.py,
activity.py) from the inbox's rows, so statuses stay the inbox's derived ones. Read-only.

The rows are the inbox's overview, not the whole history: the chart's weeks, the latest
received, and every note still to act on or flagged as a possible duplicate, however old —
the oldest are the ones past RAMQ's deadline. Every figure below only reads those."""

from datetime import date, timedelta
from decimal import Decimal

from app.claims.mapper import ClaimMapper
from app.clock import Clock, clinic_day_bounds
from app.dashboard.activity import WeeklyActivity, clinic_day_of, week_start
from app.dashboard.deadline import BillingDeadline
from app.dashboard.deadlines import DeadlineWatch
from app.dashboard.models import DashboardOut, KpisOut
from app.dashboard.tasks import TaskCounter
from app.encounters.inbox import EncounterInbox
from app.postgresdb import BillRepository, ClaimDetail, ClaimRepository
from app.shift_claims import UnclaimedShifts

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
        unclaimed_shifts: UnclaimedShifts,
        deadline: BillingDeadline,
    ) -> None:
        self._inbox = inbox
        self._claims = claims
        self._bills = bills
        self._clock = clock
        self._deadlines = deadlines
        self._activity = activity
        self._unclaimed_shifts = unclaimed_shifts
        self._deadline = deadline

    async def for_physician(self, user_id: int) -> DashboardOut:
        today = self._clock.today()
        rows = await self._inbox.overview(user_id, since=self._activity.first_day(today), latest=RECENT_COUNT)
        drafts = await self._claims.list_unbilled(user_id)
        this_week = week_start(today)
        return DashboardOut(
            today=today,
            tasks=TaskCounter.count(rows).model_copy(
                update={"unclaimed_shifts": await self._unclaimed_shifts_before(user_id, today)}
            ),
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

    async def _unclaimed_shifts_before(self, user_id: int, today: date) -> int:
        """Shifts from before today, back to the billing deadline: older ones can't be billed anymore."""
        return await self._unclaimed_shifts.count(
            user_id, today - timedelta(days=self._deadline.deadline_days), today - timedelta(days=1)
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
