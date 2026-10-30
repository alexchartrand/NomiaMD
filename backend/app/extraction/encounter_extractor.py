"""The billing pipeline run on one stored Encounter — what an intake queue
(app/intake/queue.py) runs behind `enqueue(encounter_id)`. Lives here, not in app/intake,
because the pipeline reaches into ramq_codes and the intake context never does.

Same short-session pattern as ExtractionRecorder: the encounter and its physician are read
in one scope, closed before the LLM calls."""

from app.extraction.encounter_date import parse_encounter_date
from app.extraction.factory import get_billing_pipeline
from app.extraction.pipeline import BillingPipeline
from app.extraction.recorder import ExtractionRecorder
from app.intake import NormalizerRegistry, default_normalizers
from app.llm.usage import usage_scope
from app.postgresdb import EncounterRepository, Shift, UserRepository, session_scope
from app.ramq_codes import ShiftContext
from app.shifts import EncounterSettingResolver, RunSettingSnapshot, ShiftPeriod


class EncounterNotExtractableError(Exception):
    """The encounter is gone, its physician is, it has no patient yet, or its note was
    scrubbed (app/retention/)."""


class PipelineEncounterExtractor:
    def __init__(
        self,
        recorder: ExtractionRecorder | None = None,
        normalizers: NormalizerRegistry | None = None,
        pipeline: BillingPipeline | None = None,
    ) -> None:
        """`pipeline`: None = the process's (get_billing_pipeline), looked up per extraction
        since this may be built before application_services() has set it."""
        self._recorder = recorder or ExtractionRecorder()
        self._normalizers = normalizers or default_normalizers()
        self._pipeline = pipeline
        self._snapshot = RunSettingSnapshot()

    async def extract(self, encounter_id: int) -> None:
        async with session_scope() as session:
            encounter = await EncounterRepository(session).get(encounter_id)
            user = await UserRepository(session).get_by_id(encounter.user_id) if encounter is not None else None
            setting = await EncounterSettingResolver(session).resolve(encounter) if encounter is not None else None
        if encounter is None or user is None or encounter.patient_id is None or encounter.note_text is None:
            raise EncounterNotExtractableError(encounter_id)
        assert setting is not None

        date_order = self._normalizers.for_source(encounter.source_system).date_order
        pipeline = self._pipeline or get_billing_pipeline()
        with usage_scope() as usage:
            try:
                result = await pipeline.run(
                    encounter.note_text,
                    user=user,
                    patient_id=encounter.patient_id,
                    date_order=date_order,
                    care_setting=setting.care_setting,
                    shift=_shift_context(setting.shift),
                    encounter_time=setting.start_time,
                )
            except Exception as exc:
                await self._recorder.record_failure(
                    encounter_id=encounter.id, user_id=user.id, error=exc, llm_calls=usage.records
                )
                raise

        service_date = encounter.service_date or parse_encounter_date(result.summary.encounter_setting.date, date_order)
        await self._recorder.save(
            encounter_id=encounter.id,
            user_id=user.id,
            patient_id=encounter.patient_id,
            service_date=service_date,
            result=result,
            llm_calls=usage.records,
            setting=self._snapshot.of(setting, service_date),
        )


def _shift_context(shift: Shift | None) -> ShiftContext | None:
    if shift is None:
        return None
    return ShiftContext(
        period=ShiftPeriod(shift.period),
        service_date=shift.service_date,
        start_time=shift.start_time,
        end_time=shift.end_time,
    )
