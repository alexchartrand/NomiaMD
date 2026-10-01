"""Deterministic eligibility for RAMQ code variants, from the codes table's typed bounds
(Code.eligibility) and the facts BillingContext resolves — instead of letting the model
guess an axis it was never given (panel size, registration, vulnerability, age band).

Filtering itself happens in LanceDB, before ranking (app/lancedb/eligibility.py), so a
variant that contradicts a known fact never takes one of the retrieval slots. What's left
here is pure data logic, no LLM and no DB: turning BillingContext into that filter, and
working out which unknown axes the surviving candidates still depend on."""

import math
from dataclasses import dataclass

from app.lancedb.eligibility import CodeEligibilityFilter
from app.ramq_codes.context import (
    AXIS_AGE_BAND,
    AXIS_PANEL_SIZE,
    AXIS_REGISTRATION,
    AXIS_VULNERABILITY,
    BillingContext,
)
from app.ramq_codes.models import Code


@dataclass(frozen=True)
class CandidateSet:
    candidates: list[Code]
    unresolved_axes: tuple[str, ...]


class EligibilityFilterFactory:
    """BillingContext -> CodeEligibilityFilter. Only known facts are carried over; an
    unknown one stays None, which filters nothing."""

    def from_context(self, context: BillingContext) -> CodeEligibilityFilter:
        age = context.patient.age_years
        return CodeEligibilityFilter(
            # The bounds are inclusive whole years ("moins de 80 ans" is max_age=79), so a
            # 79.6-year-old is 79 here, never rounded up to 80.
            age=math.floor(age) if age is not None else None,
            panel_size=context.physician.panel_size,
            is_registered=context.patient.is_registered,
            is_vulnerable=context.patient.is_vulnerable,
        )


# Which of a code's bounds each axis reads — an axis matters to a candidate only when one of
# them is set.
_AXIS_BOUNDS = {
    AXIS_PANEL_SIZE: lambda e: (e.min_panel_size, e.max_panel_size),
    AXIS_REGISTRATION: lambda e: (e.requires_registered,),
    AXIS_VULNERABILITY: lambda e: (e.requires_vulnerable,),
    AXIS_AGE_BAND: lambda e: (e.min_age, e.max_age),
}


class UnresolvedAxisDetector:
    """Names the axes the physician must confirm: the ones BillingContext couldn't resolve
    and at least one surviving candidate is actually bounded on. An unknown axis that no
    candidate depends on isn't worth asking about."""

    def detect(self, candidates: list[Code], context: BillingContext) -> tuple[str, ...]:
        known = context.known_axes()
        unresolved = {
            axis
            for axis, bounds in _AXIS_BOUNDS.items()
            if axis not in known and any(self._bounded(bounds(c.eligibility)) for c in candidates)
        }
        return tuple(sorted(unresolved))

    @staticmethod
    def _bounded(values: tuple) -> bool:
        return any(v is not None for v in values)

