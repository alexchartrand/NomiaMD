"""The billing context a claim snapshots at save time (see the Claim model's docstring) —
resolved by the same BillingContextBuilder the extraction pipeline uses, so "registered",
"vulnerable", age and panel size mean the same thing on a claim as they did when the codes
were suggested."""

import math
from datetime import date

from app.postgresdb import ClaimContextInput, User
from app.ramq_codes import BillingContextBuilder


class ClaimContextSnapshotter:
    def __init__(self, context_builder: BillingContextBuilder):
        self._context_builder = context_builder

    async def snapshot(self, *, physician: User, patient_id: int, service_date: date) -> ClaimContextInput:
        context = await self._context_builder.build(user=physician, patient_id=patient_id, encounter_date=service_date)
        age = context.patient.age_years
        return ClaimContextInput(
            is_registered=context.patient.is_registered,
            is_vulnerable=context.patient.is_vulnerable,
            # Completed years, like the manual's age bands.
            patient_age_years=math.floor(age) if age is not None else None,
            panel_size=context.physician.panel_size,
        )
