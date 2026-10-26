"""Renders a run's metrics (and its comparison against a baseline) as `report.md`: the run's
configuration first, then retrieval, selection, summary, cost/latency, regressions, and the
per-note tables to dig into."""

from app.benchmark.aggregate import RECALL_KS, LatencyStats, RetrievalMetrics, RunMetrics, SelectionMetrics
from app.benchmark.compare import RunComparison, SelectionComparison
from app.benchmark.records import RunManifest
from app.benchmark.scoring import CodeStatus, RetrievalScore
from app.benchmark.selection_scoring import ExpectedStatus, SelectionScore

_EXPECTED_MARKS = {
    ExpectedStatus.RETAINED: "✓",
    ExpectedStatus.POSSIBLE: "~ possible",
    ExpectedStatus.OFFERED_NOT_SELECTED: "✗ offered",
    ExpectedStatus.NOT_OFFERED: "✗ not offered",
}


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _ms(stats: LatencyStats) -> str:
    return f"{stats.p50:,.0f} / {stats.p95:,.0f} / {stats.max:,.0f}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _outcome(status: str | None, rank: int | None) -> str:
    if status is None:
        return "–"
    return f"#{rank}" if status == CodeStatus.EXACT else status


class MarkdownReport:
    def render(
        self,
        manifest: RunManifest,
        metrics: RunMetrics,
        scores: list[RetrievalScore],
        comparison: RunComparison | None = None,
        selection_scores: list[SelectionScore] | None = None,
        selection_comparison: SelectionComparison | None = None,
    ) -> str:
        lines = [f"# Benchmark run `{manifest.name}`", ""]
        lines += self._config(manifest)
        if metrics.retrieval:
            lines += self._retrieval(metrics)
        if metrics.selection:
            lines += self._selection(metrics)
        if metrics.summary:
            lines += self._summary(metrics)
        if metrics.calls:
            lines += self._cost(metrics)
        if comparison:
            lines += self._comparison(comparison)
        if selection_comparison:
            lines += self._selection_comparison(selection_comparison)
        if scores:
            lines += self._per_note(scores)
        if selection_scores:
            lines += self._selection_per_note(selection_scores)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _config(manifest: RunManifest) -> list[str]:
        c = manifest.config
        rows = [
            ["stages", ", ".join(c.stages)],
            ["query source", c.query_source],
            ["summaries from", c.summaries_from or "(this run)"],
            ["candidates from", c.candidates_from or "(this run)"],
            ["chat provider / summary model", f"{c.llm_provider} / {c.summary_model or '–'}"],
            ["selection model", c.selection_model or "–"],
            ["embeddings", f"{c.embedding_provider} / {c.embedding_model}"],
            ["codes table", f"{c.codes_table} (manual {manifest.manual_rev})"],
            ["retrieval", f"similarity_top_k={c.similarity_top_k}, fused_top_k={c.fused_top_k}, rrf_k={c.rrf_k:g}, max_family_size={c.max_family_size}, kept_sources={','.join(c.kept_sources) or '-'}"],
            ["notes", str(len(manifest.case_ids))],
            ["git", f"{(manifest.git_sha or '?')[:10]}{' (dirty)' if manifest.git_dirty else ''}"],
            ["fixture", f"{manifest.fixture_path} ({manifest.fixture_sha256[:10]})"],
            ["updated", manifest.updated_at.isoformat(timespec="seconds")],
        ]
        return _table(["", ""], rows) + [""]

    @staticmethod
    def _retrieval_row(name: str, m: RetrievalMetrics) -> list[str]:
        return [
            name,
            str(m.notes),
            str(m.expected_positions),
            *[_pct(m.recall_at[k]) for k in RECALL_KS],
            _pct(m.exact_recall),
            f"{m.mrr:.2f}",
            str(m.status_counts.get("family_only", 0)),
            str(m.status_counts.get("ineligible", 0)),
            str(m.status_counts.get("not_in_table", 0)),
            str(m.status_counts.get("not_retrieved", 0)),
            f"{m.mean_candidates:.0f}",
            str(m.errors),
        ]

    def _retrieval(self, metrics: RunMetrics) -> list[str]:
        header = [
            "group", "notes", "codes", *[f"R@{k}" for k in RECALL_KS], "recall", "MRR",
            "family", "inelig.", "no row", "missed", "cands", "errors",
        ]
        rows = [self._retrieval_row("**all**", metrics.retrieval)]
        rows += [self._retrieval_row(f"difficulty: {name}", m) for name, m in metrics.retrieval_by_difficulty.items()]
        rows += [self._retrieval_row(f"labels: {name}", m) for name, m in metrics.retrieval_by_label_status.items()]
        return [
            "## Retrieval",
            "",
            "Share of expected codes found among the candidates (R@k: within the top k). "
            "*family*: only a sibling variant was offered; *inelig.*: the billing context filters "
            "the code out (label/context/data issue, not retrieval); *no row*: not in the codes table.",
            "",
            *_table(header, rows),
            "",
        ]

    @staticmethod
    def _selection_row(name: str, m: SelectionMetrics) -> list[str]:
        return [
            name,
            str(m.notes),
            str(m.expected_positions),
            str(m.returned_codes),
            _pct(m.precision),
            _pct(m.recall),
            _pct(m.f1),
            _pct(m.exact_match_rate),
            _pct(m.overall_recall),
            f"{m.mean_possible:.1f}",
            str(m.status_counts.get("offered_not_selected", 0)),
            str(m.status_counts.get("not_offered", 0)),
            str(m.wrong_variants),
            f"{m.clean_negatives}/{m.negatives}" if m.negatives else "–",
            str(m.errors),
        ]

    def _selection(self, metrics: RunMetrics) -> list[str]:
        m = metrics.selection
        header = [
            "group", "notes", "codes", "retained", "precision", "recall", "F1", "exact notes",
            "overall recall", "possible/note", "left out", "not offered", "wrong variant", "clean negatives", "errors",
        ]
        rows = [self._selection_row("**all**", m)]
        rows += [self._selection_row(f"difficulty: {name}", g) for name, g in metrics.selection_by_difficulty.items()]
        rows += [self._selection_row(f"labels: {name}", g) for name, g in metrics.selection_by_label_status.items()]
        confidence_rows = [
            [tier, level, str(b.returned), str(b.correct), _pct(b.precision) if b.returned else "–"]
            for tier, levels in m.by_confidence.items()
            for level, b in levels.items()
        ]
        return [
            "## Selection",
            "",
            "Precision, recall, F1 and exact notes are on the codes the model is sure of (*retained*: "
            "what the review ticks), over the notes with expected codes (micro: over code positions). "
            "*overall recall*: expected codes found retained or among the other possible codes. "
            "*left out*: offered, in neither tier — a selection miss; *not offered*: a retrieval miss; "
            "*wrong variant*: a wrong retained code from an expected code's family; "
            "*clean negatives*: nothing returned in either tier.",
            "",
            *_table(header, rows),
            "",
            f"Macro precision {_pct(m.macro_precision)}, macro recall {_pct(m.macro_recall)}; "
            f"{m.mean_retained:.1f} retained and {m.mean_possible:.1f} possible codes per note; "
            f"{_pct(m.needs_confirmation_rate)} of returned codes ask for a confirmation.",
            "",
            f"Invented codes (returned but never offered, dropped): {m.invented_codes} "
            f"({_pct(m.invented_rate)} of the raw codes), in {m.notes_with_invented_codes} note(s); "
            f"malformed entries: {m.malformed_codes}.",
            "",
            *_table(["tier", "confidence", "returned", "correct", "precision"], confidence_rows),
            "",
        ]

    @staticmethod
    def _summary(metrics: RunMetrics) -> list[str]:
        s = metrics.summary
        lines = ["## Summary", "", f"{s.notes} notes, {s.errors} failed"]
        if s.error_types:
            lines[-1] += " (" + ", ".join(f"{k}: {v}" for k, v in s.error_types.items()) + ")"
        lines.append("")
        if s.checks:
            lines += _table(
                ["check", "passed", "rate"],
                [[name, f"{c.passed}/{c.applicable}", _pct(c.rate)] for name, c in s.checks.items()],
            )
            lines.append("")
        if s.stats_mean:
            lines += _table(["stat (mean per note)", "value"], [[k, f"{v:.2f}"] for k, v in s.stats_mean.items()])
            lines.append("")
        return lines

    @staticmethod
    def _cost(metrics: RunMetrics) -> list[str]:
        rows = [
            [
                g.stage,
                g.kind,
                g.purpose or "–",
                g.model,
                "yes" if g.cached else "",
                str(g.calls) + (f" ({g.errors} failed)" if g.errors else ""),
                f"{g.input_tokens:,}",
                f"{g.output_tokens:,}",
                f"{g.mean_input_tokens:,.0f} / {g.mean_output_tokens:,.0f}",
                _ms(g.latency_ms),
            ]
            for g in metrics.calls
        ]
        lines = [
            "## Cost and latency",
            "",
            *_table(
                ["stage", "kind", "purpose", "model", "cached", "calls", "input tok", "output tok",
                 "mean in / out", "latency ms p50 / p95 / max"],
                rows,
            ),
            "",
        ]
        if metrics.stage_wall_ms:
            lines += _table(
                ["stage", "wall ms per note p50 / p95 / max"],
                [[stage, _ms(stats)] for stage, stats in metrics.stage_wall_ms.items()],
            )
            lines.append("")
        return lines

    @staticmethod
    def _comparison(comparison: RunComparison) -> list[str]:
        counts = ", ".join(f"{verdict}: {n}" for verdict, n in comparison.counts.items())
        lines = [f"## Compared with `{comparison.baseline}`", "", counts, ""]
        changed = [n for n in comparison.notes if n.verdict != "unchanged"]
        if changed:
            rows = []
            for note in changed:
                moves = "; ".join(
                    f"{c.code}: {_outcome(c.before_status, c.before_rank)} → {_outcome(c.after_status, c.after_rank)}"
                    for c in note.changes
                    if c.change != "unchanged"
                )
                rows.append([note.verdict, note.patient_id, note.difficulty, moves, f"{note.before_candidates} → {note.after_candidates}"])
            lines += _table(["verdict", "note", "difficulty", "changed codes", "candidates"], rows)
            lines.append("")
        return lines

    @staticmethod
    def _selection_comparison(comparison: SelectionComparison) -> list[str]:
        counts = ", ".join(f"{verdict}: {n}" for verdict, n in comparison.counts.items())
        lines = [f"## Selection compared with `{comparison.baseline}`", "", counts, ""]
        changed = [n for n in comparison.notes if n.verdict != "unchanged"]
        if changed:
            rows = [
                [
                    note.verdict,
                    note.patient_id,
                    note.difficulty,
                    ", ".join(note.gained) or "–",
                    ", ".join(note.lost) or "–",
                    ", ".join(note.new_wrong) or "–",
                    ", ".join(note.fixed_wrong) or "–",
                    ", ".join(note.gained_overall) or "–",
                    ", ".join(note.lost_overall) or "–",
                ]
                for note in changed
            ]
            header = [
                "verdict", "note", "difficulty", "retained: gained", "lost", "new wrong", "wrong fixed",
                "overall: gained", "lost",
            ]
            lines += _table(header, rows)
            lines.append("")
        return lines

    @staticmethod
    def _selection_per_note(scores: list[SelectionScore]) -> list[str]:
        rows = []
        for score in scores:
            if score.expected:
                expected = ", ".join(f"{o.code} {_EXPECTED_MARKS[o.status]}" for o in score.expected)
            else:
                expected = "(negative)" if score.is_labeled_negative else "(unlabeled)"
            extra_retained = ", ".join(
                o.code + (f" (variant of {o.wrong_variant_of})" if o.wrong_variant_of else "")
                for o in score.retained
                if o.correct is not True
            )
            extra_possible = ", ".join(o.code for o in score.returned if not o.retained and o.correct is not True)
            rows.append([
                score.patient_id,
                score.difficulty,
                expected,
                extra_retained or "–",
                extra_possible or "–",
                str(score.dropped_not_offered) if score.dropped_not_offered else "",
                str(score.candidate_count),
                score.error or "",
            ])
        return [
            "## Selection per note",
            "",
            *_table(
                ["note", "difficulty", "expected codes", "other retained", "other possible", "invented", "cands", "error"],
                rows,
            ),
            "",
        ]

    @staticmethod
    def _per_note(scores: list[RetrievalScore]) -> list[str]:
        rows = []
        for score in scores:
            if score.outcomes:
                found = ", ".join(
                    f"{o.code} {_outcome(o.status, o.rank)}"
                    + (f" (best: {o.best_query_source} #{o.best_query_rank})" if o.best_query_source and o.status != CodeStatus.EXACT else "")
                    for o in score.outcomes
                )
            else:
                found = "(negative)" if score.is_labeled_negative else "(unlabeled)"
            rows.append([score.patient_id, score.difficulty, score.label_status, found, str(score.candidate_count), score.error or ""])
        return ["## Per note", "", *_table(["note", "difficulty", "labels", "expected codes", "cands", "error"], rows), ""]
