"""Benchmarks the extraction pipeline stage by stage over the labeled consultations/ notes
(tests/fixtures/eval_billing_codes.jsonl), storing each note's summary and retrieval result
— with every chat/embedding call's tokens and latency — under backend/benchmarks/runs/<name>/.
See app/benchmark/.

    # summaries + retrieval, the production configuration
    python scripts/benchmark.py run --name mistral-base

    # control runs: retrieve from the raw note, or from summary + note
    python scripts/benchmark.py run --name transcript-q --stages retrieval --query-source transcript
    python scripts/benchmark.py run --name combined-q --stages retrieval \\
        --query-source summary+transcript --summaries-from mistral-base

    # retrieval parameter sweep over stored summaries: no chat call, cached embeddings
    python scripts/benchmark.py sweep --summaries-from mistral-base \\
        --similarity-top-k 20,30,40 --fused-top-k 40,60

    # metrics.json + report.md, optionally against a baseline run
    python scripts/benchmark.py report combined-q --baseline mistral-base

    # copy a run into benchmarks/baselines/ (committed)
    python scripts/benchmark.py promote mistral-base --as mistral-2026-10

A summary model on another host: LLM_PROVIDER=openai_compatible LLM_ENDPOINT=... LLM_API_KEY=...
then --summary-model <name>. A re-embedded codes table: EMBEDDING_* for its model, then
--codes-table codes_<rev>. Needs DB_PATH and the embedding provider's key; chat calls only
for the summary stage. `run` re-run with the same name resumes (recorded notes are
skipped; --force redoes them)."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Loads the repo-root .env — must run before the app imports below read their settings.
import app.config  # noqa: E402,F401

from app.benchmark.commands import (  # noqa: E402
    CaseFilter,
    PromoteCommand,
    ReportCommand,
    RetrievalParams,
    RunCommand,
    RunReport,
    SweepCommand,
)
from app.benchmark.dataset import EvalSetLoader  # noqa: E402
from app.benchmark.store import RunStore  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402

STAGES = ("summary", "retrieval")


def _csv(cast):
    def parse(value: str):
        return [cast(v) for v in value.split(",") if v.strip()]

    return parse


def _add_case_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--notes", nargs="+", default=[], help="only these patient ids (e.g. CLI-2026-01220)")
    parser.add_argument("--label-status", nargs="+", default=[], help="e.g. reviewed draft-unverified")
    parser.add_argument("--difficulty", nargs="+", default=[], help="original easy medium hard negative")


def _case_filter(args) -> CaseFilter:
    return CaseFilter(tuple(args.notes), tuple(args.label_status), tuple(args.difficulty))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run stages over the notes and report")
    run.add_argument("--name", required=True)
    run.add_argument("--stages", type=_csv(str), default=list(STAGES), help="comma-separated: summary,retrieval")
    run.add_argument("--query-source", default="summary", choices=["summary", "transcript", "summary+transcript"])
    run.add_argument("--summaries-from", help="reuse this run's summaries (retrieval only)")
    run.add_argument("--summary-model", help="chat model for the summary (default: the task's)")
    run.add_argument("--similarity-top-k", type=int, default=RetrievalParams.similarity_top_k)
    run.add_argument("--fused-top-k", type=int, default=RetrievalParams.fused_top_k)
    run.add_argument("--rrf-k", type=float, default=RetrievalParams.rrf_k)
    run.add_argument("--codes-table", help="a registered codes_<rev> table instead of the current one")
    run.add_argument("--concurrency", type=int, default=2, help="notes in parallel")
    run.add_argument("--force", action="store_true", help="redo notes already recorded")
    run.add_argument("--baseline", help="compare with this run in the report")
    _add_case_filters(run)

    sweep = commands.add_parser("sweep", help="retrieval-only runs over a grid of parameters")
    sweep.add_argument("--summaries-from", required=True)
    sweep.add_argument("--similarity-top-k", type=_csv(int), default=[RetrievalParams.similarity_top_k])
    sweep.add_argument("--fused-top-k", type=_csv(int), default=[RetrievalParams.fused_top_k])
    sweep.add_argument("--rrf-k", type=_csv(float), default=[RetrievalParams.rrf_k])
    sweep.add_argument("--query-source", default="summary", choices=["summary", "transcript", "summary+transcript"])
    sweep.add_argument("--prefix", help="run name prefix (default: the summaries run)")
    sweep.add_argument("--codes-table")
    sweep.add_argument("--concurrency", type=int, default=4)
    _add_case_filters(sweep)

    report = commands.add_parser("report", help="score a run and write metrics.json + report.md")
    report.add_argument("name")
    report.add_argument("--baseline", help="compare with this run")

    promote = commands.add_parser("promote", help="copy a run into benchmarks/baselines/")
    promote.add_argument("name")
    promote.add_argument("--as", dest="as_name", required=True)
    return parser


def _print_headline(report: RunReport) -> None:
    m = report.metrics
    print(f"\n== {report.run.name}  ({report.run.path})")
    if report.fixture_changed:
        print("   note: the fixture changed since this run — scored against the current labels")
    if m.summary:
        checks = ", ".join(f"{k} {c.passed}/{c.applicable}" for k, c in m.summary.checks.items())
        print(f"   summary: {m.summary.notes} notes, {m.summary.errors} failed; checks: {checks}")
    if m.retrieval:
        r = m.retrieval
        recall_at = "  ".join(f"R@{k} {v:.0%}" for k, v in r.recall_at.items())
        counts = ", ".join(f"{k} {v}" for k, v in r.status_counts.items() if v)
        print(f"   retrieval over {r.expected_positions} expected codes: {recall_at}  MRR {r.mrr:.2f}")
        print(f"     {counts}; {r.mean_candidates:.0f} candidates/note, {r.errors} errors")
    for group in m.calls:
        cached = " cached" if group.cached else ""
        print(
            f"   {group.stage}/{group.purpose} {group.model}{cached}: {group.calls} calls, "
            f"{group.input_tokens:,} in / {group.output_tokens:,} out tokens, "
            f"p50 {group.latency_ms.p50:,.0f} ms, p95 {group.latency_ms.p95:,.0f} ms"
        )
    if report.comparison:
        print(f"   vs {report.comparison.baseline}: " + ", ".join(f"{k} {v}" for k, v in report.comparison.counts.items()))
    print(f"   report: {report.run.path / 'report.md'}")


def _print_sweep(reports: list[RunReport]) -> None:
    header = f"{'run':<60} {'R@10':>5} {'R@20':>5} {'R@40':>5} {'recall':>6} {'MRR':>5} {'cands':>5}"
    print("\n" + header + "\n" + "-" * len(header))
    for report in reports:
        r = report.metrics.retrieval
        if r is None:
            continue
        print(
            f"{report.run.name:<60} {r.recall_at[10]:>5.0%} {r.recall_at[20]:>5.0%} {r.recall_at[40]:>5.0%} "
            f"{r.exact_recall:>6.0%} {r.mrr:>5.2f} {r.mean_candidates:>5.0f}"
        )


def _progress(case, stage, ok: bool) -> None:
    print(f"  {case.patient_id:<16} {stage.name:<10} {'ok' if ok else 'FAILED'}", flush=True)


async def main() -> None:
    args = _parser().parse_args()
    configure_logging("WARNING", pretty=True)
    store = RunStore()
    loader = EvalSetLoader()
    report_command = ReportCommand(store, loader)
    run_command = RunCommand(store, loader, cache_dir=store.root / ".cache" / "embeddings")

    if args.command == "run":
        unknown = set(args.stages) - set(STAGES)
        if unknown:
            raise SystemExit(f"Unknown stage(s): {', '.join(sorted(unknown))}")
        _run, progress = await run_command.execute(
            args.name,
            stages=[s for s in STAGES if s in args.stages],
            query_source_name=args.query_source,
            summaries_from=args.summaries_from,
            summary_model=args.summary_model,
            params=RetrievalParams(args.similarity_top_k, args.fused_top_k, args.rrf_k),
            codes_table=args.codes_table,
            cases=_case_filter(args),
            concurrency=args.concurrency,
            force=args.force,
            argv=sys.argv[1:],
            on_record=_progress,
        )
        print(f"\n{progress.written} records written, {progress.skipped} already recorded, {len(progress.failed)} failed")
        for failure in progress.failed:
            print(f"  failed: {failure}")
        _print_headline(await report_command.execute(args.name, baseline=args.baseline))

    elif args.command == "sweep":
        reports = await SweepCommand(run_command, report_command).execute(
            summaries_from=args.summaries_from,
            similarity_top_ks=args.similarity_top_k,
            fused_top_ks=args.fused_top_k,
            rrf_ks=args.rrf_k,
            query_source_name=args.query_source,
            prefix=args.prefix,
            codes_table=args.codes_table,
            cases=_case_filter(args),
            concurrency=args.concurrency,
            argv=sys.argv[1:],
        )
        _print_sweep(reports)

    elif args.command == "report":
        _print_headline(await report_command.execute(args.name, baseline=args.baseline))

    elif args.command == "promote":
        baseline = PromoteCommand(store).execute(args.name, args.as_name)
        print(f"promoted to {baseline.path} — commit it to keep it")


if __name__ == "__main__":
    asyncio.run(main())
