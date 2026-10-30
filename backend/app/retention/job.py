"""The nightly retention run (app/worker.py's cron, or scripts/purge.py by hand). Each step runs
in its own session, and a failing one is logged and left for the next night: it never holds
back the others."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.clock import ClinicClock, Clock
from app.postgresdb import session_scope
from app.retention.audit import AuditEventPurge
from app.retention.note_scrub import NoteScrubber
from app.retention.policy import RetentionPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionReport:
    """Rows each step acted on — or, on a dry run, would have. None: the step failed (logged)."""

    notes_scrubbed: int | None
    audit_events_deleted: int | None


class RetentionJob:
    def __init__(self, policy: RetentionPolicy | None = None, clock: Clock | None = None) -> None:
        self._policy = policy or RetentionPolicy.from_settings()
        self._clock = clock or ClinicClock()

    async def run(self, *, dry_run: bool = False) -> RetentionReport:
        report = RetentionReport(
            notes_scrubbed=await _step("notes_scrubbed", lambda: self._scrub_notes(dry_run)),
            audit_events_deleted=await _step("audit_events_deleted", lambda: self._purge_audit_events(dry_run)),
        )
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

    async def _purge_audit_events(self, dry_run: bool) -> int:
        before = self._policy.audit_cutoff(self._clock.now())
        async with session_scope() as session:
            purge = AuditEventPurge(session)
            return await (purge.count_due(before) if dry_run else purge.purge(before))


async def _step(name: str, run: Callable[[], Awaitable[int]]) -> int | None:
    try:
        return await run()
    except Exception:
        logger.exception("retention step %s failed", name)
        return None
