"""Hands a received encounter to extraction. IntakeService only knows the queue; what runs
behind it (app/extraction/encounter_extractor.py) stays outside the intake context."""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class ExtractionQueue(Protocol):
    async def enqueue(self, encounter_id: int) -> None: ...


class EncounterExtractor(Protocol):
    """Runs the billing pipeline on one stored encounter and records the run, or the
    failure, on it."""

    async def extract(self, encounter_id: int) -> None: ...


class InlineExtractionQueue:
    """Runs the extraction before returning, in the caller's own request. Step 10 swaps in
    an arq-backed queue with the same interface."""

    def __init__(self, extractor: EncounterExtractor) -> None:
        self._extractor = extractor

    async def enqueue(self, encounter_id: int) -> None:
        # The note is already safely stored; a failed extraction shows on the encounter as
        # "échec" (the extractor records it) and must not fail its delivery.
        try:
            await self._extractor.extract(encounter_id)
        except Exception:
            logger.exception("Extraction of encounter %s failed", encounter_id)
