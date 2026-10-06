"""Code search/lookup response shapes. A hit's `fees` keep the codes table's own order: a
fee's position is the `fee_index` a claim is saved with (app/claims/models.py's
SelectedCode), the same list a billing_codes run resolves (BillingCodesTask.resolve_fees)."""

from pydantic import BaseModel

from app.ramq_codes import CodeFeeOut


class CodeHit(BaseModel):
    number: str
    description: str
    header_path: str
    fees: list[CodeFeeOut]
    # The eligibility axes this code is bound on that the patient's billing context couldn't
    # resolve, in French — empty when no patient was given (nothing to confirm against).
    needs_confirmation: list[str] = []


class CodeEligibilityOut(BaseModel):
    """Inclusive, whole units; None means no restriction on that axis."""

    min_age: int | None = None
    max_age: int | None = None
    min_panel_size: int | None = None
    max_panel_size: int | None = None
    requires_registered: bool | None = None
    requires_vulnerable: bool | None = None


class CodeDetail(CodeHit):
    when_to_use: list[str]
    rules: list[str]
    eligibility: CodeEligibilityOut
