"""The billing context a claim snapshots at save time (see the Claim model's docstring) —
resolved by the same BillingContextBuilder the extraction pipeline uses, so "registered",
"vulnerable", age and panel size mean the same thing on a claim as they did when the codes
were suggested. The same context also decides which hand-picked codes the claim may carry
(the eligibility filter), so both come from one build."""

import math
from dataclasses import dataclass
from datetime import date

from app.lancedb import CodeEligibilityFilter
from app.postgresdb import ClaimContextInput, User
from app.ramq_codes import BillingContextBuilder, EligibilityFilterFactory


@dataclass(frozen=True)
class ClaimContextSnapshot:
    # What the claim row records.
    record: ClaimContextInput
    # What a code added by hand is checked against — see app/claims/catalog.py.
    eligibility: CodeEligibilityFilter


class ClaimContextSnapshotter:
    def __init__(self, context_builder: BillingContextBuilder, filter_factory: EligibilityFilterFactory | None = None):
        self._context_builder = context_builder
        self._filter_factory = filter_factory or EligibilityFilterFactory()

    async def snapshot(self, *, physician: User, patient_id: int, service_date: date) -> ClaimContextSnapshot:
        context = await self._context_builder.build(user=physician, patient_id=patient_id, encounter_date=service_date)
        age = context.patient.age_years
        record = ClaimContextInput(
            is_registered=context.patient.is_registered,
            is_vulnerable=context.patient.is_vulnerable,
            # Completed years, like the manual's age bands.
            patient_age_years=math.floor(age) if age is not None else None,
            # An assumed panel size (no profile version in effect yet on the service date)
            # is a guess, not a fact to record on the claim.
            panel_size=context.physician.confirmed_panel_size,
        )
        return ClaimContextSnapshot(record=record, eligibility=self._filter_factory.from_context(context))
