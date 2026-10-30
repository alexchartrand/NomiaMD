"""The arq worker: `arq app.worker.WorkerSettings`. Runs extractions queued by the web
process (ArqExtractionQueue). Boots the same composition root as the API
(`application_services()`), so a job sees the same databases and billing pipeline."""

from contextlib import AsyncExitStack
from typing import Any

from arq import Retry, cron

from app.bootstrap import application_services
from app.config import settings
from app.extraction.background import (
    MAX_TRIES,
    ExtractEncounterJob,
    RetryExtraction,
    arq_redis_settings,
)
from app.logging_config import configure_logging
from app.retention import RetentionJob

configure_logging(settings.log_level)


async def on_startup(ctx: dict[str, Any]) -> None:
    stack = AsyncExitStack()
    await stack.enter_async_context(application_services())
    ctx["stack"] = stack
    ctx["extract_job"] = ExtractEncounterJob()
    ctx["retention_job"] = RetentionJob()


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["stack"].aclose()


async def extract_encounter(ctx: dict[str, Any], encounter_id: int) -> None:
    try:
        await ctx["extract_job"].run(encounter_id, attempt=ctx["job_try"])
    except RetryExtraction as retry:
        raise Retry(defer=retry.defer_seconds) from retry


async def run_retention(ctx: dict[str, Any]) -> None:
    await ctx["retention_job"].run()


class WorkerSettings:
    functions = [extract_encounter]
    # Later jobs (Epic polling) register here too. arq's cron reads the container's clock, UTC:
    # 08:00 is 03:00 or 04:00 in Montréal, outside clinic hours either way.
    cron_jobs: list[Any] = [cron(run_retention, hour=8, minute=0)]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = arq_redis_settings()
    max_jobs = settings.worker_max_jobs
    max_tries = MAX_TRIES
    # The LLM calls take a minute or more under load.
    job_timeout = 600
    # Results aren't read; dropping them lets a failed encounter be queued again.
    keep_result = 0
