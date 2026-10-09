"""IntakeService.receive end to end against the test DB, with a recording queue in place of
extraction; then the inline queue and the pipeline extractor behind it, with the pipeline
itself mocked. Seeds through session_scope (committed): the service opens its own
sessions."""

import ast
import itertools
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.care_setting import CareSetting
from app.extraction.encounter_extractor import EncounterNotExtractableError, PipelineEncounterExtractor
from app.extraction.models import ExtractionResult
from app.intake import (
    Channel,
    DedupOutcome,
    EmptyNoteError,
    EncounterMeta,
    InlineExtractionQueue,
    IntakeService,
    SourceNote,
)
from app.postgresdb import Encounter, ExtractionRun, Gender, PatientRepository, session_scope
from app.ramq_codes import BillingCodesResult
from app.summary import ConsultationSummaryResult
from tests.db_helpers import ensure_user_row, physician
from tests.test_extraction import MOCK_SUMMARY_RESULT

_physician_ids = itertools.count(5500)
# "INTS" prefix — see tests/test_intake_resolution.py's _ramq_numbers.
_ramq_numbers = itertools.count(1)


class RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list[int] = []

    async def enqueue(self, encounter_id: int) -> None:
        self.enqueued.append(encounter_id)


@pytest.fixture
async def user():
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    return user


@pytest.fixture
async def nam():
    ramq_number = f"INTS{next(_ramq_numbers):08d}"
    async with session_scope() as session:
        await PatientRepository(session).create(
            full_name="Roch Desjardins",
            ramq_number=ramq_number,
            date_of_birth=date(1981, 2, 10),
            gender=Gender.MALE,
            is_vulnerable=False,
        )
    return ramq_number


def _note(**overrides) -> SourceNote:
    fields = {"source_system": "manual", "channel": Channel.PASTE, "text": "Motif : toux depuis 3 jours."}
    return SourceNote(**(fields | overrides))


async def _get(encounter_id: int) -> Encounter:
    async with session_scope() as session:
        return await session.get(Encounter, encounter_id)


async def test_receive_with_a_known_nam_stores_and_enqueues(user, nam):
    queue = RecordingQueue()
    outcome = await IntakeService(queue).receive(_note(nam=nam, service_date="2026-03-04"), user)

    assert outcome.outcome == DedupOutcome.NEW
    assert outcome.enqueued
    assert queue.enqueued == [outcome.encounter_id]
    encounter = await _get(outcome.encounter_id)
    assert encounter.patient_id == outcome.patient_id is not None
    assert encounter.user_id == user.id
    assert encounter.channel == "paste"
    assert encounter.service_date == date(2026, 3, 4)


async def test_receive_without_a_patient_stores_but_does_not_enqueue(user):
    queue = RecordingQueue()
    service = IntakeService(queue)

    no_nam = await service.receive(_note(), user)
    unknown = await service.receive(_note(nam="ZZZZ99999999", text="Autre note."), user)

    for outcome in (no_nam, unknown):
        assert outcome.outcome == DedupOutcome.NEW
        assert outcome.patient_id is None
        assert not outcome.enqueued
        assert (await _get(outcome.encounter_id)).patient_id is None
    assert queue.enqueued == []


async def test_receive_stores_the_normalized_text(user):
    note = _note(source_system="omnimed", channel=Channel.EXTENSION, text="<p>Motif : <b>toux</b></p><p>Plan : repos</p>")
    outcome = await IntakeService(RecordingQueue()).receive(note, user)
    assert (await _get(outcome.encounter_id)).note_text == "Motif : toux\n\nPlan : repos"


async def test_receive_rejects_a_note_with_no_text_left(user):
    with pytest.raises(EmptyNoteError):
        await IntakeService(RecordingQueue()).receive(_note(source_system="omnimed", text="<script>x</script>"), user)


async def test_receive_parses_the_service_date_in_the_source_order(user):
    service = IntakeService(RecordingQueue())
    epic = await service.receive(_note(source_system="epic", service_date="03/04/2026"), user)
    manual = await service.receive(_note(service_date="03/04/2026", text="Autre note."), user)
    assert (await _get(epic.encounter_id)).service_date == date(2026, 3, 4)
    assert (await _get(manual.encounter_id)).service_date == date(2026, 4, 3)


async def test_receive_keeps_the_source_facts_as_encounter_meta(user):
    note = _note(meta=EncounterMeta(author_ref="dr-42", location_label="Urgence"), mrn="H123", batch_label="nuit")
    outcome = await IntakeService(RecordingQueue()).receive(note, user)
    assert (await _get(outcome.encounter_id)).encounter_meta == {
        "author_ref": "dr-42",
        "location_label": "Urgence",
        "mrn": "H123",
        "batch_label": "nuit",
    }


async def test_receive_stores_the_care_setting_as_its_value(user):
    note = _note(meta=EncounterMeta(care_setting=CareSetting.URGENCE))
    outcome = await IntakeService(RecordingQueue()).receive(note, user)
    assert (await _get(outcome.encounter_id)).encounter_meta == {"care_setting": "urgence"}


async def test_receive_the_same_version_twice_is_a_duplicate(user, nam):
    queue = RecordingQueue()
    service = IntakeService(queue)
    note = _note(source_system="omnimed", channel=Channel.EXTENSION, external_note_id="N-1", nam=nam)

    first = await service.receive(note, user)
    # Same note, different markup: the hash is taken after normalizing.
    second = await service.receive(note.model_copy(update={"text": f"  {note.text}\r\n"}), user)

    assert second.outcome == DedupOutcome.DUPLICATE
    assert second.encounter_id == first.encounter_id
    assert not second.enqueued
    assert queue.enqueued == [first.encounter_id]
    async with session_scope() as session:
        count = await session.scalar(select(func.count()).select_from(Encounter).where(Encounter.user_id == user.id))
    assert count == 1


async def test_receive_an_amended_note_is_a_new_version(user, nam):
    queue = RecordingQueue()
    service = IntakeService(queue)
    note = _note(source_system="omnimed", channel=Channel.EXTENSION, external_note_id="N-1", nam=nam)

    first = await service.receive(note, user)
    amended = await service.receive(note.model_copy(update={"text": f"{note.text}\nAddendum."}), user)

    assert amended.outcome == DedupOutcome.NEW_VERSION
    assert amended.encounter_id != first.encounter_id
    assert queue.enqueued == [first.encounter_id, amended.encounter_id]


async def test_receive_the_same_paste_twice_is_a_duplicate(user, nam):
    queue = RecordingQueue()
    service = IntakeService(queue)
    first = await service.receive(_note(nam=nam), user)
    again = await service.receive(_note(nam=nam), user)
    assert again.outcome == DedupOutcome.DUPLICATE
    assert again.encounter_id == first.encounter_id
    assert queue.enqueued == [first.encounter_id]


async def test_receive_keeps_every_visit_of_the_same_day(user, nam):
    # Same patient, day and author, different notes: a morning and an afternoon visit are
    # both billable, so both are stored and extracted.
    queue = RecordingQueue()
    service = IntakeService(queue)
    meta = EncounterMeta(author_ref="dr-42")
    morning = await service.receive(
        _note(nam=nam, service_date="2026-03-04", meta=meta, text="9 h : toux depuis 3 jours."), user
    )
    afternoon = await service.receive(
        _note(nam=nam, service_date="2026-03-04", meta=meta, text="15 h : revu, dyspnée nouvelle."), user
    )
    assert morning.outcome == afternoon.outcome == DedupOutcome.NEW
    assert morning.encounter_id != afternoon.encounter_id
    assert queue.enqueued == [morning.encounter_id, afternoon.encounter_id]


# --- InlineExtractionQueue ---


async def test_inline_queue_runs_the_extractor():
    extractor = AsyncMock()
    await InlineExtractionQueue(extractor).enqueue(7)
    extractor.extract.assert_awaited_once_with(7)


async def test_inline_queue_does_not_fail_the_delivery_when_extraction_fails():
    extractor = AsyncMock()
    extractor.extract.side_effect = RuntimeError("LLM indisponible")
    await InlineExtractionQueue(extractor).enqueue(7)


# --- PipelineEncounterExtractor ---


def _pipeline_results(summary_date: str):
    summary = ConsultationSummaryResult.model_validate(
        MOCK_SUMMARY_RESULT | {"encounter_setting": MOCK_SUMMARY_RESULT["encounter_setting"] | {"date": summary_date}}
    )
    return (
        ExtractionResult(task="consultation_summary", result=summary, model="mistral-small-latest"),
        ExtractionResult(task="billing_codes", result=BillingCodesResult(codes=[]), model="mistral-small-latest"),
    )


async def test_extractor_runs_the_pipeline_in_the_source_date_order(user, nam):
    outcome = await IntakeService(RecordingQueue()).receive(_note(source_system="epic", nam=nam), user)

    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(return_value=_pipeline_results("03/04/2026")),
    ) as pipeline:
        await PipelineEncounterExtractor().extract(outcome.encounter_id)

    assert pipeline.await_args.kwargs["date_order"] == "mdy"
    assert pipeline.await_args.kwargs["patient_id"] == outcome.patient_id
    encounter = await _get(outcome.encounter_id)
    assert encounter.service_date == date(2026, 3, 4)
    async with session_scope() as session:
        run = await session.scalar(select(ExtractionRun).where(ExtractionRun.encounter_id == encounter.id))
    assert run is not None


async def test_extractor_hands_the_pipeline_the_stored_care_setting(user, nam):
    note = _note(nam=nam, meta=EncounterMeta(care_setting=CareSetting.URGENCE))
    outcome = await IntakeService(RecordingQueue()).receive(note, user)

    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(return_value=_pipeline_results("2026-03-04")),
    ) as pipeline:
        await PipelineEncounterExtractor().extract(outcome.encounter_id)

    assert pipeline.await_args.kwargs["care_setting"] is CareSetting.URGENCE


async def test_extractor_without_a_care_setting_hands_the_pipeline_none(user, nam):
    outcome = await IntakeService(RecordingQueue()).receive(_note(nam=nam), user)

    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(return_value=_pipeline_results("2026-03-04")),
    ) as pipeline:
        await PipelineEncounterExtractor().extract(outcome.encounter_id)

    assert pipeline.await_args.kwargs["care_setting"] is None


async def test_extractor_records_a_pipeline_failure_on_the_encounter(user, nam):
    outcome = await IntakeService(RecordingQueue()).receive(_note(nam=nam), user)

    with patch(
        "app.extraction.encounter_extractor.run_billing_codes_pipeline",
        AsyncMock(side_effect=RuntimeError("LLM indisponible")),
    ):
        with pytest.raises(RuntimeError):
            await PipelineEncounterExtractor().extract(outcome.encounter_id)

    assert (await _get(outcome.encounter_id)).extraction_error == "RuntimeError: LLM indisponible"


async def test_extractor_refuses_an_encounter_without_a_patient(user):
    outcome = await IntakeService(RecordingQueue()).receive(_note(), user)
    with pytest.raises(EncounterNotExtractableError):
        await PipelineEncounterExtractor().extract(outcome.encounter_id)


# --- bounded context ---


def test_intake_never_imports_ramq_codes():
    intake_dir = Path(__file__).parents[1] / "app" / "intake"
    offenders = []
    for path in intake_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [f"{path.name}: {name}" for name in names if name.startswith("app.ramq_codes")]
    assert offenders == []
