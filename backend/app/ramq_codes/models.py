"""Shared RAMQ code data shapes — mirrors ramq-ingestion's src/models.py, which is where
this shape originates (Code.fees -> here). This module owns the read-side (Code, built
directly from a `codes`-table hybrid_search hit — see RAMQCodesRetriever); ramq-ingestion
owns the write-side (Code, the extraction/embedding schema, and the single flat `codes`
LanceDB table).

Also holds BillingCodesTask's own output schema (ExtractedFee/ExtractedCode/
BillingCodesResult), which is a distinct, model-facing shape rather than a mirror of the
candidate data above."""


from dataclasses import dataclass

from pydantic import BaseModel, Field


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
    when_to_use: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    fees: tuple[CodeFee, ...] = ()


class ExtractedFee(BaseModel):
    amount: float | None = Field(
        default=None, description="Fee amount in CAD, or null if none could be determined"
    )
    when_to_use: str | None = Field(
        default=None, description="The situation this fee applies to, or null if not applicable"
    )
    majoration: str | None = Field(default=None, description="Majoration detail, if any, else null")


class ExtractedCode(BaseModel):
    code: str = Field(description="RAMQ code as it appears in the reference table")
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(description="Short explanation of why this code was chosen")
    fee: ExtractedFee = Field(
        description=(
            "The fee selected from this code's candidate fee list based on the consultation "
            "summary; all sub-fields null if no fee data was available or none could be determined"
        )
    )


class BillingCodesResult(BaseModel):
    codes: list[ExtractedCode]
    notes: str | None = Field(
        default=None,
        description="Anything the model flagged as ambiguous or needing physician review",
    )
