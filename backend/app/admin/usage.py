"""The admin console's LLM usage and cost report over a range of clinic days: totals, a per-day
series and one breakdown (by model, purpose or physician). Aggregated in Python over the
range's rows rather than in SQL: days are the clinic's (America/Montreal), which SQLite and
Postgres date functions don't agree on, and a few thousand rows a month is cheap to fold.

Recent days are read from the raw `llm_calls`, older ones from their daily rollup
(app/retention/llm_usage.py) — a day is in one or the other, never both, so the report
just adds them up. A rolled-up day has no latencies left: its median and p95 are unknown."""

import enum
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.admin.pricing import PriceTable
from app.clock import clinic_day_bounds, clinic_day_of
from app.postgresdb import LLMCall, LLMCallRepository, LLMUsageDay, LLMUsageDayRepository, UserRepository


class UsageGrouping(str, enum.Enum):
    MODEL = "model"
    PURPOSE = "purpose"
    USER = "user"


@dataclass(frozen=True)
class _Usage:
    """A raw call, or a rolled-up day's calls of one model and purpose, priced."""

    day: date
    user_id: int | None
    model: str
    purpose: str | None
    in_extraction: bool
    calls: int
    input_tokens: int
    output_tokens: int
    errors: int
    # Only a raw call has one.
    latency_ms: float | None
    cost: Decimal | None

    @classmethod
    def of_call(cls, call: LLMCall, prices: PriceTable) -> "_Usage":
        return cls(
            day=clinic_day_of(call.started_at),
            user_id=call.user_id,
            model=call.model,
            purpose=call.purpose,
            in_extraction=call.run_id is not None,
            calls=1,
            input_tokens=call.input_tokens or 0,
            output_tokens=call.output_tokens or 0,
            errors=1 if call.error else 0,
            latency_ms=float(call.latency_ms),
            cost=prices.cost(call.model, call.input_tokens, call.output_tokens),
        )

    @classmethod
    def of_day(cls, row: LLMUsageDay, prices: PriceTable) -> "_Usage":
        # Per-token prices are linear: a day's totals cost what its calls did one by one.
        return cls(
            day=row.day,
            user_id=row.user_id,
            model=row.model,
            purpose=row.purpose,
            in_extraction=row.in_extraction,
            calls=row.calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            errors=row.errors,
            latency_ms=None,
            cost=prices.cost(row.model, row.input_tokens, row.output_tokens),
        )


@dataclass
class UsageBucket:
    """Totals over a set of calls. `cost` sums only priced calls; `unpriced_calls` says how
    many were left out of it. Latencies are the raw calls' only."""

    key: str
    label: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal = Decimal(0)
    unpriced_calls: int = 0
    errors: int = 0
    latencies_ms: list[float] = field(default_factory=list, repr=False)

    def add(self, usage: _Usage) -> None:
        self.calls += usage.calls
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        if usage.cost is None:
            self.unpriced_calls += usage.calls
        else:
            self.cost += usage.cost
        self.errors += usage.errors
        if usage.latency_ms is not None:
            self.latencies_ms.append(usage.latency_ms)

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
    def __init__(
        self, calls: LLMCallRepository, days: LLMUsageDayRepository, users: UserRepository, prices: PriceTable
    ) -> None:
        self._calls = calls
        self._days = days
        self._users = users
        self._prices = prices

    async def build(self, start: date, end: date, grouping: UsageGrouping) -> UsageReportResult:
        """`start` to `end`, both clinic days included."""
        since, _ = clinic_day_bounds(start)
        _, until = clinic_day_bounds(end)
        calls = await self._calls.list_between(since, until)
        usages = [_Usage.of_call(c, self._prices) for c in calls] + [
            _Usage.of_day(row, self._prices) for row in await self._days.list_between(start, end)
        ]

        totals = UsageBucket(key="total", label="Total")
        for usage in usages:
            totals.add(usage)

        extractions = len({c.run_id for c in calls if c.run_id is not None}) + sum(
            row.extractions for row in await self._days.list_extractions_between(start, end)
        )
        extraction_cost = sum((u.cost for u in usages if u.in_extraction and u.cost is not None), Decimal(0))
        labels = await self._labeller(grouping)
        return UsageReportResult(
            start=start,
            end=end,
            totals=totals,
            extractions=extractions,
            cost_per_extraction=extraction_cost / extractions if extractions else None,
            by_day=self._by_day(usages, start, end),
            grouping=grouping,
            breakdown=sorted(
                _group(usages, _GROUP_KEYS[grouping], labels).values(), key=lambda b: (-b.cost, -b.calls)
            ),
        )

    @staticmethod
    def _by_day(usages: list[_Usage], start: date, end: date) -> list[UsageBucket]:
        """Every day of the range, empty ones included, so the chart has no gaps."""
        days = {
            (start + timedelta(days=i)).isoformat(): UsageBucket(
                key=(start + timedelta(days=i)).isoformat(), label=(start + timedelta(days=i)).isoformat()
            )
            for i in range((end - start).days + 1)
        }
        for usage in usages:
            bucket = days.get(usage.day.isoformat())
            if bucket is not None:
                bucket.add(usage)
        return list(days.values())

    async def _labeller(self, grouping: UsageGrouping) -> Callable[[str], str]:
        if grouping != UsageGrouping.USER:
            return lambda key: key
        names = {str(u.id): u.full_name for u in await self._users.list_all()}
        return lambda key: names.get(key, "Sans compte")


_GROUP_KEYS: dict[UsageGrouping, Callable[[_Usage], str]] = {
    UsageGrouping.MODEL: lambda u: u.model,
    UsageGrouping.PURPOSE: lambda u: u.purpose or "autre",
    UsageGrouping.USER: lambda u: str(u.user_id) if u.user_id is not None else "none",
}


def _group(
    usages: Iterable[_Usage], key_of: Callable[[_Usage], str], label_of: Callable[[str], str]
) -> dict[str, UsageBucket]:
    buckets: dict[str, UsageBucket] = {}
    for usage in usages:
        key = key_of(usage)
        if key not in buckets:
            buckets[key] = UsageBucket(key=key, label=label_of(key))
        buckets[key].add(usage)
    return buckets
