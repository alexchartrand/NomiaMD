"""What scripts/benchmark.py's subcommands do: run, sweep, report, promote. The wiring lives
here (the benchmark's own composition root) rather than in app/bootstrap.py's
application_services(): that one guards the *current* codes table's embedding dimension at
startup, which would refuse a run against a re-embedded, non-current table of another
dimension. A benchmark only needs the RAMQ LanceDB and the model clients, and guards the
table it actually reads."""

import itertools
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.benchmark.aggregate import RunAggregator, RunMetrics
from app.benchmark.compare import RunComparator, RunComparison, SelectionComparator, SelectionComparison
from app.benchmark.dataset import BenchmarkCase, EvalSetLoader
from app.benchmark.embedding_cache import CachedEmbeddingClient
from app.benchmark.provenance import GitProvenance
from app.benchmark.query_sources import query_source
from app.benchmark.records import (
    RetrievalRecord,
    RunConfig,
    RunManifest,
    SelectionRecord,
    StageName,
    SummaryRecord,
)
from app.benchmark.report import MarkdownReport
from app.benchmark.runner import BenchmarkRunner, RunProgress
from app.benchmark.scoring import RetrievalScore, RetrievalScorer
from app.benchmark.selection_scoring import SelectionScore, SelectionScorer
from app.benchmark.stages import RetrievalStage, SelectionStage, Stage, SummaryStage
from app.benchmark.store import Run, RunStore
from app.config import settings
from app.extraction.engine import resolve_model
from app.lancedb import CodeRepository, LanceDB
from app.lancedb.database import stored_embedding
from app.lancedb.fusion import DEFAULT_K
from app.lancedb.models import CodeVersionRow
from app.llm import EmbeddingModelGuard, chat_provider, get_embedding_client
from app.ramq_codes import BillingCodesTask, build_candidate_fuser, build_code_query_runner, build_family_expander
from app.ramq_codes.candidate_fuser import DEFAULT_FUSED_TOP_K, DEFAULT_KEPT_SOURCES
from app.ramq_codes.family_expander import DEFAULT_MAX_FAMILY_SIZE
from app.ramq_codes.query_runner import DEFAULT_SIMILARITY_TOP_K
from app.summary import ConsultationSummaryTask

BACKEND_DIR = Path(__file__).parent.parent.parent


class BenchmarkConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievalParams:
    similarity_top_k: int = DEFAULT_SIMILARITY_TOP_K
    fused_top_k: int = DEFAULT_FUSED_TOP_K
    rrf_k: float = DEFAULT_K
    max_family_size: int = DEFAULT_MAX_FAMILY_SIZE
    kept_sources: tuple[str, ...] = DEFAULT_KEPT_SOURCES


@dataclass(frozen=True)
class CaseFilter:
    patient_ids: tuple[str, ...] = ()
    label_statuses: tuple[str, ...] = ()
    difficulties: tuple[str, ...] = ()


@asynccontextmanager
async def codes_repository(
    table_name: str | None, *, check_embedding_model: bool
) -> AsyncIterator[tuple[CodeRepository, CodeVersionRow]]:
    """The codes table a run reads — `table_name` pinned (current or not), or the current
    one — and its registry row."""
    db = await LanceDB.open()
    try:
        provider = db.pinned_code_tables(table_name) if table_name else db.code_tables
        version = await provider.current_version()
        if check_embedding_model:
            await EmbeddingModelGuard(get_embedding_client()).check(
                {version.table_name: await stored_embedding(await provider.current())}
            )
        yield CodeRepository(provider), version
    finally:
        db.close()


class RunCommand:
    def __init__(self, store: RunStore, loader: EvalSetLoader, cache_dir: Path):
        self._store = store
        self._loader = loader
        self._cache_dir = cache_dir

    async def execute(
        self,
        name: str,
        *,
        stages: list[StageName],
        query_source_name: str = "summary",
        summaries_from: str | None = None,
        summary_model: str | None = None,
        candidates_from: str | None = None,
        selection_model: str | None = None,
        params: RetrievalParams = RetrievalParams(),
        codes_table: str | None = None,
        cases: CaseFilter = CaseFilter(),
        concurrency: int = 2,
        force: bool = False,
        argv: list[str] | None = None,
        on_record: Callable | None = None,
    ) -> tuple[Run, RunProgress]:
        source = query_source(query_source_name)
        self._validate(stages, source.needs_summary, summaries_from, candidates_from)
        selected = self._loader.load(
            patient_ids=cases.patient_ids, label_statuses=cases.label_statuses, difficulties=cases.difficulties
        )
        if "summary" in stages or "selection" in stages:
            chat_provider()  # an unknown LLM_PROVIDER fails now, not on every note
        # Recorded resolved (argument, else LLM_MODEL_<TASK>, else the task default), so two
        # runs on different env-selected models never look alike.
        if "summary" in stages:
            summary_model = resolve_model(ConsultationSummaryTask(), summary_model)
        if "selection" in stages:
            selection_model = resolve_model(BillingCodesTask, selection_model)

        embedding_provider, embedding_model = settings.embedding_provider, settings.embedding_model
        candidates_run = self._store.open(candidates_from) if candidates_from else None
        if candidates_run is not None:
            # A selection-only run inherits how its candidates were retrieved, so its
            # manifest describes them rather than this command's unused retrieval defaults.
            retrieved = candidates_run.read_manifest().config
            summaries_from = summaries_from or self._summaries_of(candidates_run.name, retrieved)
            codes_table = self._candidates_table(codes_table, retrieved)
            source = query_source(retrieved.query_source)
            embedding_provider, embedding_model = retrieved.embedding_provider, retrieved.embedding_model
            params = RetrievalParams(
                retrieved.similarity_top_k,
                retrieved.fused_top_k,
                retrieved.rrf_k,
                retrieved.max_family_size,
                tuple(retrieved.kept_sources),
            )
        summary_run = self._store.open(summaries_from) if summaries_from else None

        async with codes_repository(codes_table, check_embedding_model="retrieval" in stages) as (codes, version):
            config = RunConfig(
                stages=stages,
                query_source=source.name,
                summaries_from=summaries_from,
                summary_model=summary_model,
                llm_provider=settings.llm_provider,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                codes_table=version.table_name,
                similarity_top_k=params.similarity_top_k,
                fused_top_k=params.fused_top_k,
                rrf_k=params.rrf_k,
                max_family_size=params.max_family_size,
                kept_sources=list(params.kept_sources),
                candidates_from=candidates_from,
                selection_model=selection_model,
            )
            run = self._open_run(name, config, version.manual_rev, selected, argv or [])

            pipeline: list[Stage] = []
            if "summary" in stages:
                pipeline.append(SummaryStage(model=summary_model))
            if "retrieval" in stages:
                query_runner = build_code_query_runner(
                    codes,
                    embedding_client=CachedEmbeddingClient(get_embedding_client(), self._cache_dir),
                    similarity_top_k=params.similarity_top_k,
                )
                candidate_fuser = build_candidate_fuser(
                    fused_top_k=params.fused_top_k, rrf_k=params.rrf_k, kept_sources=params.kept_sources
                )
                family_expander = build_family_expander(codes, max_family_size=params.max_family_size)
                pipeline.append(
                    RetrievalStage(
                        query_runner, candidate_fuser, source, summaries=summary_run, family_expander=family_expander
                    )
                )
            if "selection" in stages:
                pipeline.append(
                    SelectionStage(codes, candidates=candidates_run, summaries=summary_run, model=selection_model)
                )

            runner = BenchmarkRunner(pipeline, concurrency=concurrency, force=force, on_record=on_record)
            progress = await runner.run(run, selected)

        manifest = run.read_manifest()
        manifest.updated_at = datetime.now(timezone.utc)
        run.write_manifest(manifest)
        return run, progress

    @staticmethod
    def _validate(
        stages: list[StageName], needs_summary: bool, summaries_from: str | None, candidates_from: str | None = None
    ) -> None:
        if not stages:
            raise BenchmarkConfigError("No stage to run")
        if summaries_from and "summary" in stages:
            raise BenchmarkConfigError("--summaries-from reuses another run's summaries: drop the summary stage")
        if "retrieval" in stages and needs_summary and "summary" not in stages and not summaries_from:
            raise BenchmarkConfigError(
                "This query source needs summaries: add the summary stage or pass --summaries-from"
            )
        if candidates_from and "selection" not in stages:
            raise BenchmarkConfigError("--candidates-from only feeds the selection stage: add it")
        if candidates_from and "retrieval" in stages:
            raise BenchmarkConfigError("--candidates-from reuses another run's candidates: drop the retrieval stage")
        if "selection" in stages and "retrieval" not in stages and not candidates_from:
            raise BenchmarkConfigError("Selection needs candidates: add the retrieval stage or pass --candidates-from")
        if "selection" in stages and "summary" not in stages and not summaries_from and not candidates_from:
            raise BenchmarkConfigError("Selection needs summaries: add the summary stage or pass --summaries-from")

    @staticmethod
    def _summaries_of(candidates_name: str, retrieved: RunConfig) -> str:
        """Where the candidates run's own retrieval read its summaries: the selection prompt
        then carries the very summary its candidates were planned from."""
        if "summary" in retrieved.stages:
            return candidates_name
        if retrieved.summaries_from:
            return retrieved.summaries_from
        raise BenchmarkConfigError(
            f"Run {candidates_name!r} has no summaries (query source {retrieved.query_source!r}): pass --summaries-from"
        )

    @staticmethod
    def _candidates_table(codes_table: str | None, retrieved: RunConfig) -> str:
        if codes_table and codes_table != retrieved.codes_table:
            raise BenchmarkConfigError(
                f"The candidates were retrieved from {retrieved.codes_table}, not {codes_table}: drop --codes-table"
            )
        return retrieved.codes_table

    def _open_run(
        self, name: str, config: RunConfig, manual_rev: str, cases: list[BenchmarkCase], argv: list[str]
    ) -> Run:
        """A new run, or an existing one with the identical config (resumed: notes already
        recorded are skipped, new notes are added)."""
        now = datetime.now(timezone.utc)
        git = GitProvenance.read(BACKEND_DIR)
        case_ids = [c.patient_id for c in cases]
        if self._store.exists(name):
            run = self._store.open(name)
            manifest = run.read_manifest()
            if manifest.config != config:
                raise BenchmarkConfigError(
                    f"Run {name!r} already exists with another configuration — pick another name.\n"
                    f"  existing: {manifest.config.model_dump()}\n  new:      {config.model_dump()}"
                )
            manifest.case_ids = sorted(set(manifest.case_ids) | set(case_ids))
            manifest.argv, manifest.git_sha, manifest.git_dirty = argv, git.sha, git.dirty
        else:
            run = self._store.create(name)
            manifest = RunManifest(
                name=name,
                config=config,
                manual_rev=manual_rev,
                git_sha=git.sha,
                git_dirty=git.dirty,
                argv=argv,
                fixture_path=str(self._loader.path.relative_to(BACKEND_DIR)) if self._loader.path.is_relative_to(BACKEND_DIR) else str(self._loader.path),
                fixture_sha256=self._loader.sha256(),
                case_ids=case_ids,
                created_at=now,
                updated_at=now,
            )
        run.write_manifest(manifest)
        return run


@dataclass(frozen=True)
class RunScores:
    retrieval: list[RetrievalScore]
    selection: list[SelectionScore]


@dataclass(frozen=True)
class RunReport:
    run: Run
    manifest: RunManifest
    metrics: RunMetrics
    scores: list[RetrievalScore]
    comparison: RunComparison | None
    fixture_changed: bool
    selection_scores: list[SelectionScore] = field(default_factory=list)
    selection_comparison: SelectionComparison | None = None


class ReportCommand:
    """Scores a run against the fixture's *current* labels (so relabeling never needs a
    re-run), aggregates, optionally compares with a baseline run, and writes metrics.json and
    report.md into the run."""

    def __init__(self, store: RunStore, loader: EvalSetLoader):
        self._store = store
        self._loader = loader

    async def execute(self, name: str, *, baseline: str | None = None) -> RunReport:
        run = self._store.open(name)
        manifest = run.read_manifest()
        cases = self._loader.load(patient_ids=manifest.case_ids)
        scores = await self._scores(run, manifest, cases)

        summaries = [r for c in cases if (r := run.read("summary", c.patient_id, SummaryRecord))]
        retrievals = [r for c in cases if (r := run.read("retrieval", c.patient_id, RetrievalRecord))]
        selections = [r for c in cases if (r := run.read("selection", c.patient_id, SelectionRecord))]
        metrics = RunAggregator().aggregate(summaries, retrievals, scores.retrieval, selections, scores.selection)

        comparison = selection_comparison = None
        if baseline:
            baseline_run = self._store.open(baseline)
            baseline_manifest = baseline_run.read_manifest()
            baseline_scores = await self._scores(
                baseline_run, baseline_manifest, self._loader.load(patient_ids=baseline_manifest.case_ids)
            )
            if scores.retrieval and baseline_scores.retrieval:
                comparison = RunComparator().compare(baseline, baseline_scores.retrieval, name, scores.retrieval)
            if scores.selection and baseline_scores.selection:
                selection_comparison = SelectionComparator().compare(
                    baseline, baseline_scores.selection, name, scores.selection
                )

        run.write_json(
            "metrics.json",
            {
                "metrics": metrics.model_dump(mode="json"),
                "scores": [s.model_dump(mode="json") for s in scores.retrieval],
                "selection_scores": [s.model_dump(mode="json") for s in scores.selection],
                "comparison": comparison.model_dump(mode="json") if comparison else None,
                "selection_comparison": selection_comparison.model_dump(mode="json") if selection_comparison else None,
            },
        )
        run.write_text(
            "report.md",
            MarkdownReport().render(
                manifest, metrics, scores.retrieval, comparison, scores.selection, selection_comparison
            ),
        )
        return RunReport(
            run=run,
            manifest=manifest,
            metrics=metrics,
            scores=scores.retrieval,
            comparison=comparison,
            fixture_changed=manifest.fixture_sha256 != self._loader.sha256(),
            selection_scores=scores.selection,
            selection_comparison=selection_comparison,
        )

    @staticmethod
    async def _scores(run: Run, manifest: RunManifest, cases: list[BenchmarkCase]) -> RunScores:
        stages = manifest.config.stages
        if "retrieval" not in stages and "selection" not in stages:
            return RunScores(retrieval=[], selection=[])
        # Scored against the codes table the run retrieved from, even if another one has
        # been promoted since.
        async with codes_repository(manifest.config.codes_table, check_embedding_model=False) as (codes, _version):
            retrieval, selection = [], []
            if "retrieval" in stages:
                scorer = RetrievalScorer(codes)
                retrieval = [
                    await scorer.score(case, run.read("retrieval", case.patient_id, RetrievalRecord)) for case in cases
                ]
            if "selection" in stages:
                selection_scorer = SelectionScorer(codes)
                selection = [
                    await selection_scorer.score(case, run.read("selection", case.patient_id, SelectionRecord))
                    for case in cases
                ]
            return RunScores(retrieval=retrieval, selection=selection)


class SweepCommand:
    """One retrieval-only run per parameter combination over stored summaries — no chat call,
    and the embedding cache makes every combination after the first free."""

    def __init__(self, run_command: RunCommand, report_command: ReportCommand):
        self._run = run_command
        self._report = report_command

    async def execute(
        self,
        *,
        summaries_from: str,
        similarity_top_ks: list[int],
        fused_top_ks: list[int],
        rrf_ks: list[float],
        max_family_sizes: list[int] | None = None,
        query_source_name: str = "summary",
        prefix: str | None = None,
        codes_table: str | None = None,
        cases: CaseFilter = CaseFilter(),
        concurrency: int = 4,
        argv: list[str] | None = None,
    ) -> list[RunReport]:
        reports = []
        combinations = itertools.product(
            similarity_top_ks, fused_top_ks, rrf_ks, max_family_sizes or [DEFAULT_MAX_FAMILY_SIZE]
        )
        for similarity_top_k, fused_top_k, rrf_k, max_family_size in combinations:
            name = (
                f"{prefix or summaries_from}-{query_source_name.replace('+', '-')}"
                f"-sim{similarity_top_k}-fused{fused_top_k}-rrf{rrf_k:g}-fam{max_family_size}"
            )
            await self._run.execute(
                name,
                stages=["retrieval"],
                query_source_name=query_source_name,
                summaries_from=summaries_from,
                params=RetrievalParams(similarity_top_k, fused_top_k, rrf_k, max_family_size),
                codes_table=codes_table,
                cases=cases,
                concurrency=concurrency,
                argv=argv,
            )
            reports.append(await self._report.execute(name))
        return reports


class PromoteCommand:
    def __init__(self, store: RunStore):
        self._store = store

    def execute(self, name: str, as_name: str) -> Run:
        return self._store.promote(name, as_name)
