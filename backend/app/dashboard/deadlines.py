"""Which unbilled work is close to (or past) RAMQ's billing deadline: encounters still to
act on, and draft claims not on a bill yet. A reviewed encounter's claim stands for it, so
nothing is listed twice."""

from datetime import date

from app.dashboard.deadline import BillingDeadline
from app.dashboard.models import DeadlineItemOut
from app.dashboard.tasks import TO_DO_STATUSES
from app.encounters.masking import mask_name
from app.encounters.models import EncounterRowOut
from app.postgresdb import ClaimDetail


class DeadlineWatch:
    def __init__(self, deadline: BillingDeadline) -> None:
        self._deadline = deadline

    def items(self, rows: list[EncounterRowOut], drafts: list[ClaimDetail], today: date) -> list[DeadlineItemOut]:
        """What can still be billed first, fewest days left first; then what's past the
        deadline, most recently expired first — an item months overdue is the least
        actionable. An undated encounter has no deadline yet, so it's left out."""
        items = [
            DeadlineItemOut(
                kind="encounter",
                id=row.id,
                patient_display=row.patient.display_name if row.patient is not None else None,
                service_date=row.service_date,
                days_left=self._deadline.days_left(row.service_date, today),
            )
            for row in rows
            if row.status in TO_DO_STATUSES and row.service_date is not None
        ] + [
            DeadlineItemOut(
                kind="claim",
                id=draft.claim.id,
                patient_display=mask_name(draft.patient_full_name),
                service_date=draft.claim.service_date,
                days_left=self._deadline.days_left(draft.claim.service_date, today),
            )
            for draft in drafts
        ]
        at_risk = [item for item in items if self._deadline.is_at_risk(item.days_left)]
        return sorted(at_risk, key=lambda item: (item.days_left < 0, abs(item.days_left), item.kind, item.id))
