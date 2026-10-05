"""Background extraction: the arq-backed ExtractionQueue (the web process's side) and the
job the worker runs (app/worker.py). Which queue the web process uses is decided by
REDIS_URL — a real Redis gets this one, anything else (the "memory://" default, tests) keeps
InlineExtractionQueue."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings
from app.extraction.encounter_extractor import EncounterNotExtractableError, PipelineEncounterExtractor
from app.intake import EncounterExtractor, ExtractionQueue, InlineExtractionQueue
from app.postgresdb import ExtractionRepository, session_scope

logger = logging.getLogger(__name__)

EXTRACT_JOB_NAME = "extract_encounter"
MAX_TRIES = 3
RETRY_BACKOFF_SECONDS = 15


def redis_is_configured(redis_url: str) -> bool:
    return redis_url.startswith(("redis://", "rediss://", "unix://"))


def arq_redis_settings() -> RedisSettings:
    if not redis_is_configured(settings.redis_url):
        return RedisSettings()  # localhost default; a worker started without REDIS_URL can't connect
    return RedisSettings.from_dsn(settings.redis_url)


class ArqExtractionQueue:
    """Hands the encounter to the worker and returns at once."""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue(self, encounter_id: int) -> None:
        # The job id dedups an encounter that is already waiting or running; keep_result=0
        # (WorkerSettings) frees it once finished, so a later retry can be queued again.
        await self._pool.enqueue_job(EXTRACT_JOB_NAME, encounter_id, _job_id=f"extract-{encounter_id}")


@asynccontextmanager
async def extraction_queue(extractor: EncounterExtractor | None = None) -> AsyncIterator[ExtractionQueue]:
    if not redis_is_configured(settings.redis_url):
        yield InlineExtractionQueue(extractor or PipelineEncounterExtractor())
        return
    pool = await create_pool(arq_redis_settings())
    try:
        yield ArqExtractionQueue(pool)
    finally:
        await pool.aclose()


class RetryExtraction(Exception):
    """The attempt failed and another one is allowed; carries the delay before it."""

    def __init__(self, defer_seconds: int) -> None:
        super().__init__(defer_seconds)
        self.defer_seconds = defer_seconds


class ExtractEncounterJob:
    """One encounter's extraction as a job: idempotent, and retried with a growing delay.
    The extractor records the failure on the encounter ("échec") on every attempt, so the
    inbox shows it while retries are pending."""

    def __init__(self, extractor: EncounterExtractor | None = None) -> None:
        self._extractor = extractor or PipelineEncounterExtractor()

    async def run(self, encounter_id: int, attempt: int) -> None:
        if await self._has_run(encounter_id):
            logger.info("Encounter %s already extracted; skipping", encounter_id)
            return
        try:
            await self._extractor.extract(encounter_id)
        except EncounterNotExtractableError:
            # Gone, or no patient yet (the pick queues it again): retrying can't help.
            logger.warning("Encounter %s is not extractable; dropping the job", encounter_id)
        except Exception as exc:
            if attempt >= MAX_TRIES:
                raise
            logger.warning("Extraction of encounter %s failed (attempt %s); retrying", encounter_id, attempt)
            raise RetryExtraction(RETRY_BACKOFF_SECONDS * attempt) from exc

    async def _has_run(self, encounter_id: int) -> bool:
        async with session_scope() as session:
            return encounter_id in await ExtractionRepository(session).latest_run_ids([encounter_id])
