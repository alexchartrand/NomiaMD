"""The arq worker: `arq app.worker.WorkerSettings`. Runs extractions queued by the web
process (ArqExtractionQueue). Boots the same composition root as the API
(`application_services()`), so a job sees the same databases and task registry."""

from contextlib import AsyncExitStack
from typing import Any

from arq import Retry

from app.bootstrap import application_services
from app.config import settings
from app.extraction.background import (
    MAX_TRIES,
    ExtractEncounterJob,
    RetryExtraction,
    arq_redis_settings,
)
from app.logging_config import configure_logging

configure_logging(settings.log_level)


async def on_startup(ctx: dict[str, Any]) -> None:
    stack = AsyncExitStack()
    await stack.enter_async_context(application_services())
    ctx["stack"] = stack
    ctx["extract_job"] = ExtractEncounterJob()


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["stack"].aclose()


async def extract_encounter(ctx: dict[str, Any], encounter_id: int) -> None:
    try:
        await ctx["extract_job"].run(encounter_id, attempt=ctx["job_try"])
    except RetryExtraction as retry:
        raise Retry(defer=retry.defer_seconds) from retry



class WorkerSettings:
    functions = [extract_encounter]
    # Later jobs (retention purge, Epic polling) register here: cron(fn, hour=3, minute=0).
    cron_jobs: list[Any] = []
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = arq_redis_settings()
    max_jobs = settings.worker_max_jobs
    max_tries = MAX_TRIES
    # The LLM calls take a minute or more under load.
    job_timeout = 600
    # Results aren't read; dropping them lets a failed encounter be queued again.
    keep_result = 0
