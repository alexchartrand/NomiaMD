"""The billing pipeline run on one stored Encounter — what an intake queue
(app/intake/queue.py) runs behind `enqueue(encounter_id)`. Lives here, not in app/intake,
because the pipeline reaches into ramq_codes and the intake context never does.

Same short-session pattern as ExtractionRecorder: the encounter and its physician are read
in one scope, closed before the LLM calls."""

from app.care_setting import parse_care_setting
from app.extraction.encounter_date import parse_encounter_date
from app.extraction.pipeline import run_billing_codes_pipeline
from app.extraction.recorder import ExtractionRecorder
from app.intake import NormalizerRegistry, default_normalizers
from app.postgresdb import EncounterRepository, UserRepository, session_scope


class EncounterNotExtractableError(Exception):
    """The encounter is gone, its physician is, or it has no patient yet."""


class PipelineEncounterExtractor:
    def __init__(self, recorder: ExtractionRecorder | None = None, normalizers: NormalizerRegistry | None = None) -> None:
        self._recorder = recorder or ExtractionRecorder()
        self._normalizers = normalizers or default_normalizers()

    async def extract(self, encounter_id: int) -> None:
        async with session_scope() as session:
            encounter = await EncounterRepository(session).get(encounter_id)
            user = await UserRepository(session).get_by_id(encounter.user_id) if encounter is not None else None
        if encounter is None or user is None or encounter.patient_id is None:
            raise EncounterNotExtractableError(encounter_id)

        date_order = self._normalizers.for_source(encounter.source_system).date_order
        try:
            summary_result, billing_result = await run_billing_codes_pipeline(
                encounter.note_text,
                user=user,
                patient_id=encounter.patient_id,
                date_order=date_order,
                care_setting=parse_care_setting((encounter.encounter_meta or {}).get("care_setting")),
            )
        except Exception as exc:
            await self._recorder.record_failure(encounter_id=encounter.id, user_id=user.id, error=exc)
            raise

        await self._recorder.save(
            encounter_id=encounter.id,
            user_id=user.id,
            patient_id=encounter.patient_id,
            service_date=parse_encounter_date(summary_result.result.encounter_setting.date, date_order),
            stages=[summary_result, billing_result],
        )
