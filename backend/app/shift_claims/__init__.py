"""Billing a shift itself, not a patient: the curated shift codes (catalog/shift_codes.yaml —
09791, 19953), the rules that suggest them from a shift's care setting, hours and day types,
and the shift claim the physician confirms them as (no patient, no NAM), billed alongside
patient claims.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory directly."""

from app.shift_claims.factory import shift_code_catalog, unclaimed_shifts
from app.shift_claims.mapper import ShiftClaimMapper
from app.shift_claims.models import ShiftClaimOut
from app.shift_claims.pending import UnclaimedShifts
from app.shift_claims.router import shift_billing_router, shift_claims_router
from app.shift_claims.rules import ShiftCodeRules

__all__ = [
    "ShiftClaimMapper",
    "ShiftClaimOut",
    "ShiftCodeRules",
    "UnclaimedShifts",
    "shift_billing_router",
    "shift_claims_router",
    "shift_code_catalog",
    "unclaimed_shifts",
]
