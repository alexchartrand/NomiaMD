"""How long each kind of record is kept, from config (app/config.py's `retention_*`). The
privacy policy (frontend/src/pages/Privacy.tsx) names the same periods."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.clock import clinic_day_bounds
from app.config import settings
from app.postgresdb import ScrubCutoffs


@dataclass(frozen=True)
class RetentionPolicy:
    # A note's text: this long after its visit (past RAMQ's 90-day billing deadline)...
    note_unbilled_days: int = 180
    # ...and at least this long after the last change to its live claim (billed, billed
    # again after a refusal, edited), so the back-and-forth with RAMQ keeps the note.
    note_after_claim_days: int = 365
    audit_days: int = 365
    # Raw llm_calls rows; older days live on as daily totals (app/retention/llm_usage.py).
    llm_raw_days: int = 90

    @classmethod
    def from_settings(cls) -> "RetentionPolicy":
        return cls(
            note_unbilled_days=settings.retention_note_unbilled_days,
            note_after_claim_days=settings.retention_note_after_claim_days,
            audit_days=settings.retention_audit_days,
            llm_raw_days=settings.retention_llm_raw_days,
        )

    def scrub_cutoffs(self, today: date, now: datetime) -> ScrubCutoffs:
        """A note is due the day after its `note_unbilled_days`-th day: 180 days after the
        visit it is still kept, at 181 it goes."""
        visit_before = today - timedelta(days=self.note_unbilled_days)
        return ScrubCutoffs(
            visit_before=visit_before,
            received_before=clinic_day_bounds(visit_before)[0],
            claim_changed_before=now - timedelta(days=self.note_after_claim_days),
            restored_before=now - timedelta(days=self.note_unbilled_days),
        )

    def audit_cutoff(self, now: datetime) -> datetime:
        return now - timedelta(days=self.audit_days)

    def llm_rollup_before(self, today: date) -> datetime:
        """Calls started before this instant are rolled up: the start of the oldest clinic day
        still kept raw, so only whole days are folded."""
        return clinic_day_bounds(today - timedelta(days=self.llm_raw_days))[0]
