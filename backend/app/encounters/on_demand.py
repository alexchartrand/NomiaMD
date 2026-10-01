"""`POST /encounters/{id}/extract`: runs one encounter's extraction now, in the request,
and returns it — a retry after "échec", or a re-run. Same short-session pattern as POST
/extract: the ownership check and the read-back each open their own session_scope, and
none is held across the LLM calls."""

from app.extraction.models import BillingExtractionResponse
from app.extraction.stored import StoredExtractionLoader
from app.intake import EncounterExtractor, EncounterNotFoundError
from app.postgresdb import EncounterRepository, User, session_scope


class EncounterHasNoPatientError(ValueError):
    """Still "à associer": there's no billing context to extract against until a patient is
    picked (POST /encounters/{id}/patient)."""


class OnDemandExtraction:
    def __init__(self, extractor: EncounterExtractor) -> None:
        self._extractor = extractor

    async def run(self, encounter_id: int, user: User) -> BillingExtractionResponse:
        async with session_scope() as session:
            encounter = await EncounterRepository(session).get_for_user(encounter_id, user.id)
        if encounter is None:
            raise EncounterNotFoundError(encounter_id)
        if encounter.patient_id is None:
            raise EncounterHasNoPatientError(encounter_id)

        # A failure is recorded on the encounter ("échec") by the extractor, then raised.
        await self._extractor.extract(encounter_id)

        async with session_scope() as session:
            # Re-read: the run may have set the encounter's service date.
            encounter = await EncounterRepository(session).get_for_user(encounter_id, user.id)
            extraction = await StoredExtractionLoader(session).latest_one(encounter) if encounter else None
        if extraction is None:
            raise EncounterNotFoundError(encounter_id)
        return extraction
