"""Folds llm_calls past their raw retention into daily totals, then deletes them — so usage
(tokens per physician, model and purpose; extractions per day) stays reportable for good
while each call's detail doesn't. Folding and deleting happen in the caller's one transaction:
a day is either still raw or rolled up, never both, and a rerun finds nothing to fold."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import clinic_day_of
from app.postgresdb import ExtractionUsageDay, LLMCall, LLMCallRepository, LLMUsageDay, LLMUsageDayRepository

_UsageKey = tuple[date, int | None, str, str, str, str | None, bool]


@dataclass
class _DayTotals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: int = 0
    latency_ms_total: Decimal = Decimal(0)

    def add(self, call: LLMCall) -> None:
        self.calls += 1
        self.input_tokens += call.input_tokens or 0
        self.output_tokens += call.output_tokens or 0
        self.errors += 1 if call.error else 0
        self.latency_ms_total += Decimal(call.latency_ms)


@dataclass
class _Fold:
    usage: dict[_UsageKey, _DayTotals] = field(default_factory=lambda: defaultdict(_DayTotals))
    runs: dict[tuple[date, int | None], set[int]] = field(default_factory=lambda: defaultdict(set))

    def add(self, call: LLMCall) -> None:
        day = clinic_day_of(call.started_at)
        key = (day, call.user_id, call.kind, call.provider, call.model, call.purpose, call.run_id is not None)
        self.usage[key].add(call)
        if call.run_id is not None:
            self.runs[(day, call.user_id)].add(call.run_id)

    @property
    def days(self) -> list[date]:
        return sorted({key[0] for key in self.usage})


class LLMUsageRollup:
    def __init__(self, session: AsyncSession) -> None:
        self._calls = LLMCallRepository(session)
        self._days = LLMUsageDayRepository(session)

    async def count_due(self, before: datetime) -> int:
        return await self._calls.count_before(before)

    async def roll_up(self, before: datetime) -> int:
        """Every call started before `before` — a clinic day's start, so whole days only. Returns
        how many raw calls were folded and deleted."""
        calls = await self._calls.list_before(before)
        if not calls:
            return 0
        fold = _Fold()
        for call in calls:
            fold.add(call)
        days = fold.days
        await self._merge_usage(fold, days[0], days[-1])
        await self._merge_extractions(fold, days[0], days[-1])
        await self._calls.delete_before(before)
        return len(calls)

    async def _merge_usage(self, fold: _Fold, first: date, last: date) -> None:
        # A day already rolled up only gets more rows if a late call arrived for it.
        existing = {_usage_key(row): row for row in await self._days.list_between(first, last)}
        rows = []
        for key, totals in fold.usage.items():
            row = existing.get(key) or _new_usage_row(key)
            row.calls += totals.calls
            row.input_tokens += totals.input_tokens
            row.output_tokens += totals.output_tokens
            row.errors += totals.errors
            row.latency_ms_total += totals.latency_ms_total
            rows.append(row)
        await self._days.add_many(rows)

    async def _merge_extractions(self, fold: _Fold, first: date, last: date) -> None:
        existing = {(row.day, row.user_id): row for row in await self._days.list_extractions_between(first, last)}
        rows = []
        for (day, user_id), runs in fold.runs.items():
            row = existing.get((day, user_id)) or ExtractionUsageDay(day=day, user_id=user_id, extractions=0)
            row.extractions += len(runs)
            rows.append(row)
        await self._days.add_many(rows)


def _usage_key(row: LLMUsageDay) -> _UsageKey:
    return (row.day, row.user_id, row.kind, row.provider, row.model, row.purpose, row.in_extraction)


def _new_usage_row(key: _UsageKey) -> LLMUsageDay:
    day, user_id, kind, provider, model, purpose, in_extraction = key
    return LLMUsageDay(
        day=day,
        user_id=user_id,
        kind=kind,
        provider=provider,
        model=model,
        purpose=purpose,
        in_extraction=in_extraction,
        calls=0,
        input_tokens=0,
        output_tokens=0,
        errors=0,
        latency_ms_total=Decimal(0),
    )
