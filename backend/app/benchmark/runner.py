"""Runs a run's stages over its cases: notes in parallel (bounded — chat APIs rate-limit),
stages in order within a note (retrieval may read the summary just written). Resumable: a
note's stage that already has a record is skipped unless forced, so an interrupted run picks
up where it stopped."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from app.benchmark.dataset import BenchmarkCase
from app.benchmark.stages import Stage
from app.benchmark.store import Run

logger = logging.getLogger(__name__)


@dataclass
class RunProgress:
    written: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)


class BenchmarkRunner:
    def __init__(
        self,
        stages: list[Stage],
        *,
        concurrency: int = 2,
        force: bool = False,
        on_record: Callable[[BenchmarkCase, Stage, bool], None] | None = None,
    ):
        """`on_record(case, stage, ok)` is called after each stage record is written."""
        self._stages = stages
        self._semaphore = asyncio.Semaphore(concurrency)
        self._force = force
        self._on_record = on_record

    async def run(self, run: Run, cases: list[BenchmarkCase]) -> RunProgress:
        progress = RunProgress()
        await asyncio.gather(*(self._run_case(run, case, progress) for case in cases))
        return progress

    async def _run_case(self, run: Run, case: BenchmarkCase, progress: RunProgress) -> None:
        async with self._semaphore:
            for stage in self._stages:
                if not self._force and run.has(stage.name, case.patient_id):
                    progress.skipped += 1
                    continue
                record = await stage.run(case, run)
                run.write(stage.name, record)
                progress.written += 1
                if record.error is not None:
                    progress.failed.append(f"{case.patient_id}/{stage.name}: {record.error.type}")
                    logger.warning(
                        "benchmark stage failed",
                        extra={"patient_id": case.patient_id, "stage": stage.name, "error": record.error.message},
                    )
                if self._on_record:
                    self._on_record(case, stage, record.error is None)
