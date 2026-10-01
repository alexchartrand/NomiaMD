"""The read side of the inbox: a period's encounters as list rows, or one encounter in full.
Works in the session it's given; never makes an LLM call."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import clinic_day_bounds
from app.encounters.duplicates import DuplicateFlagger
from app.encounters.masking import mask_name, mask_nam
from app.encounters.models import EncounterDetailOut, EncounterRowOut, MaskedPatientOut, PatientOut
from app.encounters.readiness import is_all_clean
from app.extraction.stored import StoredExtractionLoader
from app.intake import status_of
from app.postgresdb import (
    EncounterActivity,
    EncounterPeriod,
    EncounterRepository,
    Patient,
    PatientRepository,
    ReceivedWindow,
)


class EncounterInbox:
    def __init__(self, session: AsyncSession, flagger: DuplicateFlagger | None = None) -> None:
        self._flagger = flagger or DuplicateFlagger()
        self._encounters = EncounterRepository(session)
        self._patients = PatientRepository(session)
        self._extractions = StoredExtractionLoader(session)

    async def period(self, user_id: int, first: date | None, last: date | None) -> list[EncounterRowOut]:
        """Service dates `first` through `last`, both included; either may be open — a
        physician who bills at the end of the week reads several days at once."""
        received = ReceivedWindow(
            start=clinic_day_bounds(first)[0] if first is not None else None,
            end=clinic_day_bounds(last)[1] if last is not None else None,
        )
        activities = await self._encounters.list_in_period(user_id, EncounterPeriod(first, last, received))
        encounters = [activity.encounter for activity in activities]
        extractions = await self._extractions.latest(encounters)
        patient_ids = {e.patient_id for e in encounters if e.patient_id is not None}
        patients = {p.id: p for p in await self._patients.get_many(list(patient_ids))} if patient_ids else {}
        duplicates = self._flagger.flags(encounters)
        rows = []
        for activity in activities:
            encounter = activity.encounter
            status = status_of(activity)
            extraction = extractions.get(encounter.id)
            patient = patients.get(encounter.patient_id) if encounter.patient_id is not None else None
            possible_duplicate_ids = duplicates.get(encounter.id, [])
            rows.append(
                EncounterRowOut(
                    id=encounter.id,
                    status=status,
                    patient=_masked(patient),
                    source_system=encounter.source_system,
                    channel=encounter.channel,
                    batch_label=_batch_label(activity),
                    service_date=encounter.service_date,
                    received_at=encounter.created_at,
                    code_count=len(extraction.billing.result.codes) if extraction is not None else None,
                    extraction_run_id=extraction.extraction_run_id if extraction is not None else None,
                    possible_duplicate_ids=possible_duplicate_ids,
                    all_clean=is_all_clean(
                        status,
                        extraction,
                        service_date=encounter.service_date,
                        possible_duplicate=bool(possible_duplicate_ids),
                    ),
                )
            )
        return rows

    async def detail(self, user_id: int, encounter_id: int) -> EncounterDetailOut | None:
        activity = await self._encounters.activity_for_user(encounter_id, user_id)
        if activity is None:
            return None
        encounter = activity.encounter
        # Deleted patients included, same as PatientRepository.get_many: what was received
        # stays readable.
        patients = await self._patients.get_many([encounter.patient_id]) if encounter.patient_id is not None else []
        return EncounterDetailOut(
            id=encounter.id,
            status=status_of(activity),
            patient=_full(patients[0]) if patients else None,
            source_system=encounter.source_system,
            channel=encounter.channel,
            external_note_id=encounter.external_note_id,
            external_encounter_id=encounter.external_encounter_id,
            batch_label=_batch_label(activity),
            service_date=encounter.service_date,
            received_at=encounter.created_at,
            meta=encounter.encounter_meta or {},
            duplicate_of_id=encounter.duplicate_of_id,
            note_text=encounter.note_text,
            extraction_error=encounter.extraction_error,
            extraction=await self._extractions.latest_one(encounter),
        )


def _batch_label(activity: EncounterActivity) -> str | None:
    return (activity.encounter.encounter_meta or {}).get("batch_label")


def _masked(patient: Patient | None) -> MaskedPatientOut | None:
    if patient is None:
        return None
    return MaskedPatientOut(id=patient.id, display_name=mask_name(patient.full_name), nam=mask_nam(patient.ramq_number))


def _full(patient: Patient) -> PatientOut:
    return PatientOut(id=patient.id, full_name=patient.full_name, nam=patient.ramq_number)
