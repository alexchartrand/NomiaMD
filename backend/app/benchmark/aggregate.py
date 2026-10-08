"""Run-level numbers from the per-note records and scores: retrieval recall, selection
precision/recall, summary check pass rates, and what every call cost (tokens, latency) — overall and per difficulty / label
status, since an average can hide a group that regressed."""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from app.benchmark.records import RetrievalRecord, SelectionRecord, StageRecord, SummaryRecord
from app.benchmark.scoring import CodeStatus, RetrievalScore
from app.benchmark.selection_scoring import ExpectedStatus, SelectionScore

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


class ConfidenceBucket(BaseModel):
    returned: int
    correct: int
    precision: float


class SelectionMetrics(BaseModel):
    notes: int
    errors: int
    # Notes with expected codes. Precision, recall and F1 are over their code positions and
    # the codes the model is sure of (`retained`): what the review ticks and approving bills.
    positive_notes: int
    expected_positions: int
    returned_codes: int
    true_positives: int
    precision: float
    recall: float
    f1: float
    # Means of the per-note values, so a note with many codes doesn't outweigh the others.
    macro_precision: float
    macro_recall: float
    # Positive notes whose retained codes are exactly the expected ones.
    exact_match_rate: float
    # Expected codes found in either tier (retained or only possible).
    overall_recall: float
    # Codes per note (every note), in each tier.
    mean_retained: float
    mean_possible: float
    status_counts: dict[str, int]
    # Wrong retained codes from an expected code's family: the right act, the wrong variant.
    wrong_variants: int
    negatives: int
    # Nothing returned, in either tier.
    clean_negatives: int
    # Over every returned code (unlabeled notes included).
    needs_confirmation_rate: float
    # Precision per tier ("retained" / "possible") and confidence level, on positive notes.
    by_confidence: dict[str, dict[str, ConfidenceBucket]]
    # Codes the model returned that were never offered (dropped by parse()).
    invented_codes: int
    notes_with_invented_codes: int
    malformed_codes: int
    # Share of the model's raw codes that parse() dropped as invented.
    invented_rate: float


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
    selection: SelectionMetrics | None = None
    selection_by_difficulty: dict[str, SelectionMetrics] = {}
    selection_by_label_status: dict[str, SelectionMetrics] = {}
    calls: list[CallGroup] = []
    stage_wall_ms: dict[str, LatencyStats] = {}


class RunAggregator:
    def aggregate(
        self,
        summaries: list[SummaryRecord],
        retrievals: list[RetrievalRecord],
        scores: list[RetrievalScore],
        selections: list[SelectionRecord] | None = None,
        selection_scores: list[SelectionScore] | None = None,
    ) -> RunMetrics:
        selections = selections or []
        metrics = RunMetrics()
        if summaries:
            metrics.summary = self._summary(summaries)
        if scores:
            metrics.retrieval = self._retrieval(scores)
            metrics.retrieval_by_difficulty = self._grouped(scores, lambda s: s.difficulty, self._retrieval)
            metrics.retrieval_by_label_status = self._grouped(scores, lambda s: s.label_status, self._retrieval)
        if selection_scores:
            metrics.selection = self._selection(selection_scores)
            metrics.selection_by_difficulty = self._grouped(selection_scores, lambda s: s.difficulty, self._selection)
            metrics.selection_by_label_status = self._grouped(selection_scores, lambda s: s.label_status, self._selection)
        records_by_stage = {"summary": summaries, "retrieval": retrievals, "selection": selections}
        metrics.calls = self._calls(records_by_stage)
        metrics.stage_wall_ms = {
            stage: LatencyStats.of(r.totals.wall_ms for r in records)
            for stage, records in records_by_stage.items()
            if records
        }
        return metrics

    @staticmethod
    def _grouped(scores: list, key, metrics_of) -> dict:
        groups: dict[str, list] = defaultdict(list)
        for score in scores:
            groups[key(score)].append(score)
        return {name: metrics_of(group) for name, group in sorted(groups.items())}

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
    def _selection(scores: list[SelectionScore]) -> SelectionMetrics:
        positives = [s for s in scores if s.expected]
        negatives = [s for s in scores if s.is_labeled_negative]
        expected = [o for s in positives for o in s.expected]
        retained_on_positives = [o for s in positives for o in s.retained]
        true_positives = sum(s.true_positives for s in positives)
        precision = true_positives / len(retained_on_positives) if retained_on_positives else 0.0
        recall = true_positives / len(expected) if expected else 0.0

        def mean(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        def bucket(outcomes: list) -> ConfidenceBucket:
            correct = sum(1 for o in outcomes if o.correct)
            return ConfidenceBucket(
                returned=len(outcomes), correct=correct, precision=correct / len(outcomes) if outcomes else 0.0
            )

        returned_on_positives = [o for s in positives for o in s.returned]
        by_confidence = {
            tier: {
                level: bucket([o for o in returned_on_positives if o.retained == is_retained and o.confidence == level])
                for level in ("high", "medium", "low")
            }
            for tier, is_retained in (("retained", True), ("possible", False))
        }

        every_returned = [o for s in scores for o in s.returned]
        invented = sum(s.dropped_not_offered for s in scores)
        raw_codes = sum(s.raw_code_count for s in scores)
        return SelectionMetrics(
            notes=len(scores),
            errors=sum(1 for s in scores if s.error),
            positive_notes=len(positives),
            expected_positions=len(expected),
            returned_codes=len(retained_on_positives),
            true_positives=true_positives,
            precision=precision,
            recall=recall,
            f1=2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            macro_precision=mean([s.true_positives / len(s.retained) if s.retained else 0.0 for s in positives]),
            macro_recall=mean([s.true_positives / len(s.expected) for s in positives]),
            exact_match_rate=mean([1.0 if s.exact_match else 0.0 for s in positives]),
            overall_recall=sum(s.found_overall for s in positives) / len(expected) if expected else 0.0,
            mean_retained=mean([float(len(s.retained)) for s in scores]),
            mean_possible=mean([float(len(s.returned) - len(s.retained)) for s in scores]),
            status_counts={status.value: sum(1 for o in expected if o.status == status) for status in ExpectedStatus},
            wrong_variants=sum(1 for o in retained_on_positives if o.wrong_variant_of),
            negatives=len(negatives),
            clean_negatives=sum(1 for s in negatives if s.clean_negative),
            needs_confirmation_rate=mean([1.0 if o.needs_confirmation else 0.0 for o in every_returned]),
            by_confidence=by_confidence,
            invented_codes=invented,
            notes_with_invented_codes=sum(1 for s in scores if s.dropped_not_offered),
            malformed_codes=sum(s.dropped_malformed for s in scores),
            invented_rate=invented / raw_codes if raw_codes else 0.0,
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
