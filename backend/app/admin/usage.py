"""The admin console's LLM usage and cost report over a range of clinic days: totals, a per-day
series and one breakdown (by model, purpose or physician). Aggregated in Python over the
range's rows rather than in SQL: days are the clinic's (America/Montreal), which SQLite and
Postgres date functions don't agree on, and a few thousand rows a month is cheap to fold."""

import enum
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.admin.pricing import PriceTable
from app.clock import CLINIC_ZONE, clinic_day_bounds
from app.postgresdb import LLMCall, LLMCallRepository, UserRepository


class UsageGrouping(str, enum.Enum):
    MODEL = "model"
    PURPOSE = "purpose"
    USER = "user"


@dataclass
class UsageBucket:
    """Totals over a set of calls. `cost` sums only priced calls; `unpriced_calls` says how
    many were left out of it."""

    key: str
    label: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal = Decimal(0)
    unpriced_calls: int = 0
    errors: int = 0
    latencies_ms: list[float] = field(default_factory=list, repr=False)

    def add(self, call: LLMCall, cost: Decimal | None) -> None:
        self.calls += 1
        self.input_tokens += call.input_tokens or 0
        self.output_tokens += call.output_tokens or 0
        if cost is None:
            self.unpriced_calls += 1
        else:
            self.cost += cost
        if call.error:
            self.errors += 1
        self.latencies_ms.append(float(call.latency_ms))

    @property
    def median_latency_ms(self) -> float | None:
        return statistics.median(self.latencies_ms) if self.latencies_ms else None

    @property
    def p95_latency_ms(self) -> float | None:
        if len(self.latencies_ms) < 2:
            return self.median_latency_ms
        return statistics.quantiles(self.latencies_ms, n=20)[-1]


@dataclass(frozen=True)
class UsageReportResult:
    start: date
    end: date
    totals: UsageBucket
    extractions: int
    cost_per_extraction: Decimal | None
    by_day: list[UsageBucket]
    grouping: UsageGrouping
    breakdown: list[UsageBucket]


class UsageReport:
    def __init__(self, calls: LLMCallRepository, users: UserRepository, prices: PriceTable) -> None:
        self._calls = calls
        self._users = users
        self._prices = prices

    async def build(self, start: date, end: date, grouping: UsageGrouping) -> UsageReportResult:
        """`start` to `end`, both clinic days included."""
        since, _ = clinic_day_bounds(start)
        _, until = clinic_day_bounds(end)
        calls = await self._calls.list_between(since, until)
        costs = [self._prices.cost(c.model, c.input_tokens, c.output_tokens) for c in calls]
        priced = list(zip(calls, costs))

        totals = UsageBucket(key="total", label="Total")
        for call, cost in priced:
            totals.add(call, cost)

        extraction_runs = {c.run_id for c in calls if c.run_id is not None}
        extraction_cost = sum(
            (cost for call, cost in priced if call.run_id is not None and cost is not None), Decimal(0)
        )
        labels = await self._labeller(grouping)
        return UsageReportResult(
            start=start,
            end=end,
            totals=totals,
            extractions=len(extraction_runs),
            cost_per_extraction=extraction_cost / len(extraction_runs) if extraction_runs else None,
            by_day=self._by_day(priced, start, end),
            grouping=grouping,
            breakdown=sorted(
                _group(priced, _GROUP_KEYS[grouping], labels).values(), key=lambda b: (-b.cost, -b.calls)
            ),
        )

    @staticmethod
    def _by_day(priced: list[tuple[LLMCall, Decimal | None]], start: date, end: date) -> list[UsageBucket]:
        """Every day of the range, empty ones included, so the chart has no gaps."""
        days = {
            (start + timedelta(days=i)).isoformat(): UsageBucket(
                key=(start + timedelta(days=i)).isoformat(), label=(start + timedelta(days=i)).isoformat()
            )
            for i in range((end - start).days + 1)
        }
        for call, cost in priced:
            bucket = days.get(_clinic_day(call.started_at).isoformat())
            if bucket is not None:
                bucket.add(call, cost)
        return list(days.values())

    async def _labeller(self, grouping: UsageGrouping) -> Callable[[str], str]:
        if grouping != UsageGrouping.USER:
            return lambda key: key
        names = {str(u.id): u.full_name for u in await self._users.list_all()}
        return lambda key: names.get(key, "Sans compte")


_GROUP_KEYS: dict[UsageGrouping, Callable[[LLMCall], str]] = {
    UsageGrouping.MODEL: lambda c: c.model,
    UsageGrouping.PURPOSE: lambda c: c.purpose or "autre",
    UsageGrouping.USER: lambda c: str(c.user_id) if c.user_id is not None else "none",
}


def _group(
    priced: Iterable[tuple[LLMCall, Decimal | None]], key_of: Callable[[LLMCall], str], label_of: Callable[[str], str]
) -> dict[str, UsageBucket]:
    buckets: dict[str, UsageBucket] = {}
    for call, cost in priced:
        key = key_of(call)
        if key not in buckets:
            buckets[key] = UsageBucket(key=key, label=label_of(key))
        buckets[key].add(call, cost)
    return buckets


def _clinic_day(instant: datetime) -> date:
    # SQLite hands timestamps back naive; they were stored in UTC.
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(CLINIC_ZONE).date()
