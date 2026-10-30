"""Removes the clinical text of encounters past retention, and nothing else: the encounter row,
its runs' codes and its claims stay, so billing history and RAMQ follow-ups outlive the note.

Removed: the note (`note_text`), the extraction error that may quote it, each run's clinical
summary (the whole `consultation_summary` result) and what the `billing_codes` result restates
from the note (BillingCodesResult.without_note_text). Each encounter is scrubbed with its
results together, in the caller's transaction."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.postgresdb import Encounter, EncounterRepository, ExtractionRepository, ScrubCutoffs
from app.ramq_codes import BillingCodesResult, CodeSelector
from app.summary import ConsultationSummarizer


@dataclass(frozen=True)
class ScrubOutcome:
    encounters: int
    summaries_removed: int
    selections_redacted: int


class NoteScrubber:
    def __init__(self, session: AsyncSession) -> None:
        self._encounters = EncounterRepository(session)
        self._extractions = ExtractionRepository(session)

    async def count_due(self, cutoffs: ScrubCutoffs) -> int:
        return await self._encounters.count_due_for_scrub(cutoffs)

    async def scrub_due(self, cutoffs: ScrubCutoffs, now: datetime) -> ScrubOutcome:
        return await self.scrub(await self._encounters.list_due_for_scrub(cutoffs), now)

    async def scrub(self, encounters: list[Encounter], now: datetime) -> ScrubOutcome:
        summaries = selections = 0
        for result in await self._extractions.results_of_encounters([e.id for e in encounters]):
            if result.task == ConsultationSummarizer.NAME:
                await self._extractions.delete_result(result)
                summaries += 1
            elif result.task == CodeSelector.NAME:
                redacted = BillingCodesResult.model_validate(result.result_json).without_note_text()
                await self._extractions.replace_result(result, redacted.model_dump(mode="json"))
                selections += 1
        for encounter in encounters:
            await self._encounters.scrub_note(encounter, now)
        return ScrubOutcome(encounters=len(encounters), summaries_removed=summaries, selections_redacted=selections)
