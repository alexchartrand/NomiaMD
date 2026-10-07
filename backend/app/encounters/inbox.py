"""The read side of the inbox: a period's encounters as list rows, or one encounter in full.
Works in the session it's given; never makes an LLM call."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.mapper import ClaimMapper
from app.clock import clinic_day_bounds
from app.encounters.duplicates import DuplicateFlagger
from app.encounters.masking import mask_name, mask_nam
from app.encounters.models import EncounterDetailOut, EncounterRowOut, MaskedPatientOut, PatientOut
from app.encounters.readiness import is_all_clean
from app.encounters.row_billing import RowBillingSummarizer
from app.extraction.stored import StoredExtractionLoader
from app.intake import status_of
from app.patients.registration import resolve_registration
from app.postgresdb import (
    ClaimRepository,
    EncounterActivity,
    EncounterPeriod,
    EncounterRepository,
    OverviewScope,
    Patient,
    PatientRepository,
    ReceivedWindow,
    User,
)


class EncounterInbox:
    def __init__(self, session: AsyncSession, flagger: DuplicateFlagger | None = None) -> None:
        self._flagger = flagger or DuplicateFlagger()
        self._row_billing = RowBillingSummarizer()
        self._encounters = EncounterRepository(session)
        self._patients = PatientRepository(session)
        self._extractions = StoredExtractionLoader(session)
        self._claims = ClaimRepository(session)

    async def period(self, user_id: int, first: date | None, last: date | None) -> list[EncounterRowOut]:
        """Service dates `first` through `last`, both included; either may be open — a
        physician who bills at the end of the week reads several days at once."""
        activities = await self._encounters.list_in_period(user_id, _period(first, last))
        return await self._rows(user_id, activities)

    async def overview(self, user_id: int, since: date, latest: int) -> list[EncounterRowOut]:
        """Enough rows to summarize the physician's work without reading all of it: service
        dates from `since` on, the `latest` received, and — however old — every row still to
        act on or flagged as a possible duplicate (EncounterRepository.list_for_overview).
        Statuses, `all_clean` and duplicate flags are exact for every row returned."""
        activities = await self._encounters.list_for_overview(
            user_id, OverviewScope(window=_period(since, None), latest=latest)
        )
        return await self._rows(user_id, activities)

    async def _rows(self, user_id: int, activities: list[EncounterActivity]) -> list[EncounterRowOut]:
        encounters = [activity.encounter for activity in activities]
        extractions = await self._extractions.latest(encounters)
        claims = await self._claims.live_for_encounters(user_id, [e.id for e in encounters])
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
            billing = self._row_billing.summarize(claims.get(encounter.id), extraction)
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
                    code_count=billing.code_count,
                    codes=billing.codes,
                    indicative_total=billing.indicative_total,
                    extraction_run_id=extraction.extraction_run_id if extraction is not None else None,
                    possible_duplicate_ids=possible_duplicate_ids,
                    deletable=not activity.has_live_claim,
                    all_clean=is_all_clean(
                        status,
                        extraction,
                        service_date=encounter.service_date,
                        possible_duplicate=bool(possible_duplicate_ids),
                    ),
                )
            )
        return rows

    async def detail(self, user: User, encounter_id: int) -> EncounterDetailOut | None:
        activity = await self._encounters.activity_for_user(encounter_id, user.id)
        if activity is None:
            return None
        encounter = activity.encounter
        # Deleted patients included, same as PatientRepository.get_many: what was received
        # stays readable.
        patients = await self._patients.get_many([encounter.patient_id]) if encounter.patient_id is not None else []
        claim = (await self._claims.live_for_encounters(user.id, [encounter.id])).get(encounter.id)
        return EncounterDetailOut(
            id=encounter.id,
            status=status_of(activity),
            patient=_full(patients[0], user) if patients else None,
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
            claim=ClaimMapper.from_detail(claim) if claim is not None else None,
        )


def _period(first: date | None, last: date | None) -> EncounterPeriod:
    received = ReceivedWindow(
        start=clinic_day_bounds(first)[0] if first is not None else None,
        end=clinic_day_bounds(last)[1] if last is not None else None,
    )
    return EncounterPeriod(first, last, received)


def _batch_label(activity: EncounterActivity) -> str | None:
    return (activity.encounter.encounter_meta or {}).get("batch_label")


def _masked(patient: Patient | None) -> MaskedPatientOut | None:
    if patient is None:
        return None
    return MaskedPatientOut(id=patient.id, display_name=mask_name(patient.full_name), nam=mask_nam(patient.ramq_number))


def _full(patient: Patient, physician: User) -> PatientOut:
    return PatientOut(
        id=patient.id,
        full_name=patient.full_name,
        nam=patient.ramq_number,
        date_of_birth=patient.date_of_birth,
        is_vulnerable=patient.is_vulnerable,
        is_registered=resolve_registration(patient.family_doctor_practice_number, physician.practice_number),
    )
