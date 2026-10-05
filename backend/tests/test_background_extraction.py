"""Step 10: the extraction job (idempotent, retried), the arq queue, and the queue chosen by
REDIS_URL. The pipeline is patched, as in test_intake_service.py; arq's pool is a stub."""

import itertools
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import get_current_user
from app.config import settings
from app.extraction.background import (
    MAX_TRIES,
    ArqExtractionQueue,
    ExtractEncounterJob,
    RetryExtraction,
    extraction_queue,
)
from app.intake import EncounterStatus, InlineExtractionQueue, IntakeService
from app.intake.status import status_of
from app.main import app
from app.postgresdb import EncounterRepository, ExtractionRun, Gender, PatientRepository, session_scope
from app.worker import WorkerSettings, extract_encounter
from tests.db_helpers import ensure_user_row, physician
from tests.test_intake_service import RecordingQueue, _get, _note, _pipeline_results

_physician_ids = itertools.count(6100)
_ramq_numbers = itertools.count(1)  # "BGEX" prefix


@pytest.fixture
async def received():
    """A received encounter with a known patient, not yet extracted."""
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    ramq_number = f"BGEX{next(_ramq_numbers):08d}"
    async with session_scope() as session:
        await PatientRepository(session).create(
            full_name="Roch Desjardins",
            ramq_number=ramq_number,
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=False,
        )
    outcome = await IntakeService(RecordingQueue()).receive(_note(nam=ramq_number), user)
    return user, outcome.encounter_id


async def _run_count(encounter_id: int) -> int:
    async with session_scope() as session:
        return await session.scalar(
            select(func.count()).select_from(ExtractionRun).where(ExtractionRun.encounter_id == encounter_id)
        )


async def test_job_runs_the_pipeline_once_even_when_run_twice(received):
    _, encounter_id = received
    job = ExtractEncounterJob()
    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(return_value=_pipeline_results("2026-03-04")),
    ) as pipeline:
        await job.run(encounter_id, attempt=1)
        await job.run(encounter_id, attempt=1)

    assert pipeline.await_count == 1
    assert await _run_count(encounter_id) == 1


async def test_failed_attempt_records_the_error_and_asks_for_a_retry(received):
    _, encounter_id = received
    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(side_effect=RuntimeError("LLM indisponible")),
    ):
        with pytest.raises(RetryExtraction) as retry:
            await ExtractEncounterJob().run(encounter_id, attempt=1)

    assert retry.value.defer_seconds > 0
    assert "LLM indisponible" in (await _get(encounter_id)).extraction_error
    async with session_scope() as session:
        activity = await EncounterRepository(session).activity_for_user(encounter_id, received[0].id)
    assert status_of(activity) == EncounterStatus.ECHEC


async def test_last_attempt_fails_for_good(received):
    _, encounter_id = received
    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(side_effect=RuntimeError("LLM indisponible")),
    ):
        with pytest.raises(RuntimeError):
            await ExtractEncounterJob().run(encounter_id, attempt=MAX_TRIES)


async def test_retry_backoff_grows_with_the_attempt(received):
    _, encounter_id = received
    delays = []
    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        for attempt in (1, 2):
            with pytest.raises(RetryExtraction) as retry:
                await ExtractEncounterJob().run(encounter_id, attempt=attempt)
            delays.append(retry.value.defer_seconds)
    assert delays[1] > delays[0]


async def test_a_missing_encounter_is_dropped_not_retried():
    await ExtractEncounterJob().run(999_999_999, attempt=1)


async def test_arq_job_turns_a_retry_into_arq_retry():
    job = AsyncMock()
    job.run.side_effect = RetryExtraction(30)
    with pytest.raises(Retry) as retry:
        await extract_encounter({"extract_job": job, "job_try": 1}, 5)
    assert retry.value.defer_score == 30_000
    job.run.assert_awaited_once_with(5, attempt=1)


def test_worker_settings():
    assert WorkerSettings.functions == [extract_encounter]
    assert WorkerSettings.max_tries == MAX_TRIES
    assert WorkerSettings.max_jobs == settings.worker_max_jobs


async def test_arq_queue_enqueues_one_job_per_encounter():
    pool = MagicMock(enqueue_job=AsyncMock())
    await ArqExtractionQueue(pool).enqueue(12)
    pool.enqueue_job.assert_awaited_once_with("extract_encounter", 12, _job_id="extract-12")


async def test_queue_is_inline_without_a_real_redis(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "memory://")
    async with extraction_queue() as queue:
        assert isinstance(queue, InlineExtractionQueue)


async def test_queue_is_arq_with_a_redis_url(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    pool = MagicMock(aclose=AsyncMock())
    with patch("app.extraction.background.create_pool", AsyncMock(return_value=pool)):
        async with extraction_queue() as queue:
            assert isinstance(queue, ArqExtractionQueue)
    pool.aclose.assert_awaited_once()


async def test_extract_route_without_wait_queues_the_encounter(received):
    user, encounter_id = received
    app.dependency_overrides[get_current_user] = lambda: user
    queue = RecordingQueue()
    with TestClient(app) as client:
        app.state.extraction_queue = queue
        response = client.post(f"/encounters/{encounter_id}/extract?wait=false")
    assert response.status_code == 202
    assert queue.enqueued == [encounter_id]
    assert await _run_count(encounter_id) == 0
