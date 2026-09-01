"""Shared RAMQ code data shapes — mirrors ramq-ingestion's src/models.py, which is where
this shape originates (Code.fees -> here). This module owns the read-side (Code, built
directly from a `codes`-table hybrid_search hit — see RAMQCodesRetriever); ramq-ingestion
owns the write-side (Code, the extraction/embedding schema, and the single flat `codes`
LanceDB table).

Also holds BillingCodesTask's own output schema (CodeFeeOut/ExtractedCode/
BillingCodesResult), which is a distinct, model-facing shape rather than a mirror of the
candidate data above."""


from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class CodeFee:
    amount: float | None
    amount_text: str | None
    context: str | None
    lieu: str | None
    majoration: str | None


@dataclass(frozen=True)
class Code:
    number: str
    libelle: str
    description: str
    # The manual's taxonomy path in full (see app/lancedb/models.py's CodeRow.header_path
    # for why it's kept whole rather than trimmed to a "meaningful" suffix). Used by
    # CodeFamilySelector to group near-duplicate variants and by BillingCodesTask's prompt
    # to show the axes (vulnerability, registration, age band, panel size) that distinguish
    # one family member from another.
    header_path: str = ""
    when_to_use: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    fees: tuple[CodeFee, ...] = ()


class CodeFeeOut(BaseModel):
    """A candidate's real fee entry, resolved server-side (see BillingCodesTask.resolve_fees)
    — mirrors CodeFee/CodeRowFee field-for-field. Never populated by the model; the physician
    picks among these in the review UI when a code has more than one."""

    amount: float | None = None
    amount_text: str | None = None
    context: str | None = None
    lieu: str | None = None
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
