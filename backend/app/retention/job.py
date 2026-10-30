"""The nightly retention run (app/worker.py's cron, or scripts/purge.py by hand). Each step runs
in its own session, so one failing never holds back the others."""

import logging
from dataclasses import dataclass

from app.clock import ClinicClock, Clock
from app.postgresdb import session_scope
from app.retention.note_scrub import NoteScrubber
from app.retention.policy import RetentionPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionReport:
    """Rows each step acted on — or, on a dry run, would have."""

    notes_scrubbed: int


class RetentionJob:
    def __init__(self, policy: RetentionPolicy | None = None, clock: Clock | None = None) -> None:
        self._policy = policy or RetentionPolicy.from_settings()
        self._clock = clock or ClinicClock()

    async def run(self, *, dry_run: bool = False) -> RetentionReport:
        report = RetentionReport(notes_scrubbed=await self._scrub_notes(dry_run))
        logger.info("retention_run", extra={"dry_run": dry_run, **vars(report)})
        return report

    async def _scrub_notes(self, dry_run: bool) -> int:
        now = self._clock.now()
        cutoffs = self._policy.scrub_cutoffs(self._clock.today(), now)
        async with session_scope() as session:
            scrubber = NoteScrubber(session)
            if dry_run:
                return await scrubber.count_due(cutoffs)
            return (await scrubber.scrub_due(cutoffs, now)).encounters
