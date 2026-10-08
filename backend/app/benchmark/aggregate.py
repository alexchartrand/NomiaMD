"""Run-level numbers from the per-note records and scores: retrieval recall, summary check
pass rates, and what every call cost (tokens, latency) — overall and per difficulty / label
status, since an average can hide a group that regressed."""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from app.benchmark.records import RetrievalRecord, StageRecord, SummaryRecord
from app.benchmark.scoring import CodeStatus, RetrievalScore

RECALL_KS = (5, 10, 20, 40)


class LatencyStats(BaseModel):
    n: int
    mean: float
    p50: float
    p95: float
    max: float

    @classmethod
    def of(cls, values: Iterable[float]) -> "LatencyStats":
        ordered = sorted(values)
        if not ordered:
            return cls(n=0, mean=0.0, p50=0.0, p95=0.0, max=0.0)
        return cls(
            n=len(ordered),
            mean=sum(ordered) / len(ordered),
            p50=_percentile(ordered, 50),
            p95=_percentile(ordered, 95),
            max=ordered[-1],
        )


def _percentile(ordered: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already sorted list."""
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


class RetrievalMetrics(BaseModel):
    notes: int
    expected_positions: int
    status_counts: dict[str, int]
    # Share of expected-code positions found at rank <= k.
    recall_at: dict[int, float]
    exact_recall: float
    # Mean of 1/rank over expected positions (0 when not in the candidates).
    mrr: float
    mean_candidates: float
    mean_queries: float
    errors: int


class SummaryCheckRate(BaseModel):
    passed: int
    applicable: int
    rate: float


class SummaryMetrics(BaseModel):
    notes: int
    errors: int
    error_types: dict[str, int]
    checks: dict[str, SummaryCheckRate]
    stats_mean: dict[str, float]


class CallGroup(BaseModel):
    stage: str
    kind: str
    purpose: str | None
    model: str
    cached: bool
    calls: int
    errors: int
    input_tokens: int
    output_tokens: int
    mean_input_tokens: float
    mean_output_tokens: float
    latency_ms: LatencyStats


class RunMetrics(BaseModel):
    summary: SummaryMetrics | None = None
    retrieval: RetrievalMetrics | None = None
    retrieval_by_difficulty: dict[str, RetrievalMetrics] = {}
    retrieval_by_label_status: dict[str, RetrievalMetrics] = {}
    calls: list[CallGroup] = []
    stage_wall_ms: dict[str, LatencyStats] = {}


class RunAggregator:
    def aggregate(
        self,
        summaries: list[SummaryRecord],
        retrievals: list[RetrievalRecord],
        scores: list[RetrievalScore],
    ) -> RunMetrics:
        metrics = RunMetrics()
        if summaries:
            metrics.summary = self._summary(summaries)
        if scores:
            metrics.retrieval = self._retrieval(scores)
            metrics.retrieval_by_difficulty = self._grouped(scores, lambda s: s.difficulty)
            metrics.retrieval_by_label_status = self._grouped(scores, lambda s: s.label_status)
        metrics.calls = self._calls({"summary": summaries, "retrieval": retrievals})
        metrics.stage_wall_ms = {
            stage: LatencyStats.of(r.totals.wall_ms for r in records)
            for stage, records in (("summary", summaries), ("retrieval", retrievals))
            if records
        }
        return metrics

    def _grouped(self, scores: list[RetrievalScore], key) -> dict[str, RetrievalMetrics]:
        groups: dict[str, list[RetrievalScore]] = defaultdict(list)
        for score in scores:
            groups[key(score)].append(score)
        return {name: self._retrieval(group) for name, group in sorted(groups.items())}

    @staticmethod
    def _retrieval(scores: list[RetrievalScore]) -> RetrievalMetrics:
        outcomes = [o for s in scores for o in s.outcomes]
        positions = len(outcomes)
        ranks = [o.rank for o in outcomes if o.status == CodeStatus.EXACT and o.rank is not None]

        def share(count: int) -> float:
            return count / positions if positions else 0.0

        return RetrievalMetrics(
            notes=len(scores),
            expected_positions=positions,
            status_counts={status.value: sum(1 for o in outcomes if o.status == status) for status in CodeStatus},
            recall_at={k: share(sum(1 for r in ranks if r <= k)) for k in RECALL_KS},
            exact_recall=share(len(ranks)),
            mrr=sum(1 / r for r in ranks) / positions if positions else 0.0,
            mean_candidates=sum(s.candidate_count for s in scores) / len(scores) if scores else 0.0,
            mean_queries=sum(s.query_count for s in scores) / len(scores) if scores else 0.0,
            errors=sum(1 for s in scores if s.error),
        )

    @staticmethod
    def _summary(records: list[SummaryRecord]) -> SummaryMetrics:
        ok = [r for r in records if r.result is not None]
        check_names = sorted({c.name for r in ok for c in r.checks})
        checks = {}
        for name in check_names:
            applicable = [c for r in ok for c in r.checks if c.name == name and c.passed is not None]
            passed = sum(1 for c in applicable if c.passed)
            checks[name] = SummaryCheckRate(
                passed=passed, applicable=len(applicable), rate=passed / len(applicable) if applicable else 0.0
            )
        stat_names = sorted({k for r in ok for k in r.stats})
        return SummaryMetrics(
            notes=len(records),
            errors=len(records) - len(ok),
            error_types=dict(Counter(r.error.type for r in records if r.error)),
            checks=checks,
            stats_mean={
                name: sum(float(r.stats.get(name, 0)) for r in ok) / len(ok) if ok else 0.0 for name in stat_names
            },
        )

    @staticmethod
    def _calls(records_by_stage: dict[str, list[StageRecord]]) -> list[CallGroup]:
        groups: dict[tuple, list] = defaultdict(list)
        for stage, records in records_by_stage.items():
            for record in records:
                for call in record.calls:
                    groups[(stage, call.kind, call.purpose, call.model, call.cached)].append(call)

        result = []
        for (stage, kind, purpose, model, cached), calls in sorted(groups.items(), key=lambda kv: [str(x) for x in kv[0]]):
            succeeded = [c for c in calls if c.error is None]
            input_tokens = sum(c.input_tokens or 0 for c in succeeded)
            output_tokens = sum(c.output_tokens or 0 for c in succeeded)
            result.append(
                CallGroup(
                    stage=stage,
                    kind=kind,
                    purpose=purpose,
                    model=model,
                    cached=cached,
                    calls=len(calls),
                    errors=len(calls) - len(succeeded),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    mean_input_tokens=input_tokens / len(succeeded) if succeeded else 0.0,
                    mean_output_tokens=output_tokens / len(succeeded) if succeeded else 0.0,
                    latency_ms=LatencyStats.of(c.latency_ms for c in calls),
                )
            )
        return result
