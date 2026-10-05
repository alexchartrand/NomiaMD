"""FastAPI dependencies for the /encounters routes."""

from fastapi import Request

from app.encounters.duplicates import DuplicateDecisions
from app.encounters.inbox import EncounterInbox
from app.encounters.on_demand import OnDemandExtraction
from app.encounters.removal import EncounterRemoval
from app.extraction.encounter_extractor import PipelineEncounterExtractor
from app.intake import ExtractionQueue
from app.postgresdb import DbSession


def get_encounter_inbox(session: DbSession) -> EncounterInbox:
    return EncounterInbox(session)


def get_duplicate_decisions(session: DbSession) -> DuplicateDecisions:
    return DuplicateDecisions(session)


def get_encounter_removal(session: DbSession) -> EncounterRemoval:
    return EncounterRemoval(session)


def get_on_demand_extraction() -> OnDemandExtraction:
    return OnDemandExtraction(PipelineEncounterExtractor())


def get_extraction_queue(request: Request) -> ExtractionQueue:
    return request.app.state.extraction_queue
