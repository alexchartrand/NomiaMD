"""FastAPI dependencies for the /encounters routes, and the IntakeService app/main.py
builds at startup — wired here because this is where intake meets extraction."""

from app.encounters.duplicates import DuplicateDecisions
from app.encounters.inbox import EncounterInbox
from app.encounters.on_demand import OnDemandExtraction
from app.extraction.encounter_extractor import PipelineEncounterExtractor
from app.intake import InlineExtractionQueue, IntakeService
from app.postgresdb import DbSession


def get_encounter_inbox(session: DbSession) -> EncounterInbox:
    return EncounterInbox(session)


def get_duplicate_decisions(session: DbSession) -> DuplicateDecisions:
    return DuplicateDecisions(session)


def get_on_demand_extraction() -> OnDemandExtraction:
    return OnDemandExtraction(PipelineEncounterExtractor())


def build_intake_service() -> IntakeService:
    """The note's extraction runs inline, in the request that delivered it. Step 10 picks an
    arq-backed queue here instead, by config."""
    return IntakeService(InlineExtractionQueue(PipelineEncounterExtractor()))
