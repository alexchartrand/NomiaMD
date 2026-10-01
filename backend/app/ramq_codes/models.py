"""Shared RAMQ code data shapes — mirrors ramq-ingestion's src/ramq_ingestion/codes/schema/
(code.py, fee.py), which is where this shape originates. This module owns the read-side
(Code, built directly from a hybrid_search hit on the current `codes_<rev>` table — see
RAMQCodesRetriever); ramq-ingestion owns the write-side (Code, the extraction/embedding
schema, and one flat `codes_<rev>` LanceDB table per manual revision).

Also holds BillingCodesTask's own output schema (CodeFeeOut/ExtractedCode/
BillingCodesResult), which is a distinct, model-facing shape rather than a mirror of the
candidate data above."""


from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["high", "medium", "low"]

# "unités" means `amount` counts anesthesia base units, not dollars (typically an R = 2
# column) — never billed as a dollar amount, see app/claims/fees.py's FeeSnapshotter.
FeeUnit = Literal["dollars", "unités"]


@dataclass(frozen=True)
class CodeFee:
    amount: float | None
    amount_text: str | None
    context: str | None
    majoration: str | None
    lieux: tuple[str, ...] = ()
    # The manual's raw role column (R = 1, R = 2, R = 7...), None for a single-amount table.
    # Section-specific meaning, so never mapped to one meaning per number.
    role: int | None = None
    unit: FeeUnit = "dollars"


@dataclass(frozen=True)
class CodeEligibility:
    """The code's typed eligibility bounds. Inclusive, whole units; None means no restriction
    on that axis (never "unknown") — see app/lancedb/models.py's CodeRow."""

    min_age: int | None = None
    max_age: int | None = None
    min_panel_size: int | None = None
    max_panel_size: int | None = None
    requires_registered: bool | None = None
    requires_vulnerable: bool | None = None


@dataclass(frozen=True)
class Code:
    number: str
    description: str
    # The manual's taxonomy path in full. Shown in BillingCodesTask's prompt so the model
    # can see what distinguishes this candidate from a near-identical sibling.
    header_path: str = ""
    when_to_use: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    fees: tuple[CodeFee, ...] = ()
    eligibility: CodeEligibility = CodeEligibility()


class CodeFeeOut(BaseModel):
    """A candidate's real fee entry, resolved server-side (see BillingCodesTask.resolve_fees)
    — mirrors CodeFee/CodeRowFee field-for-field. Never populated by the model; the physician
    picks among these in the review UI when a code has more than one."""

    amount: float | None = None
    amount_text: str | None = None
    role: int | None = None
    unit: FeeUnit = "dollars"
    context: str | None = None
    lieux: list[str] = []
    majoration: str | None = None


class ExtractedCode(BaseModel):
    code: str = Field(description="RAMQ code as it appears in the reference table")
    description: str
    # A three-level bucket, not a 0-1 float: an LLM's confidence score isn't a calibrated
    # probability, and "high/medium/low" is what the review UI actually sorts/filters by.
    confidence: ConfidenceLevel = Field(description="How well-supported this code is by the consultation summary")
    explanation: str = Field(description="Short explanation of why this code was chosen")
    supporting_quote: str = Field(
        description=(
            "A verbatim quote from the consultation summary or transcript that grounds this "
            "code — the cheapest possible check a physician has against a hallucinated match"
        )
    )
    needs_confirmation: list[str] = Field(
        default_factory=list,
        description=(
            "Plain-language facts the physician must confirm before billing this code — e.g. "
            "'panel size not on file: confirm this is the <500-patient variant' — one entry per "
            "unresolved axis this code's candidate family couldn't be disambiguated on. Empty "
            "when every relevant fact was already known."
        ),
    )
    fees: list[CodeFeeOut] = Field(
        default_factory=list,
        json_schema_extra={"server_only": True},
        description=(
            "The candidate's real fee list, resolved server-side after the LLM call — never "
            "populated by the model. Empty when no fee data was available."
        ),
    )


class BillingCodesResult(BaseModel):
    codes: list[ExtractedCode]
    notes: str | None = Field(
        default=None,
        description="Anything the model flagged as ambiguous or needing physician review",
    )
