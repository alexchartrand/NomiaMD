from pydantic import BaseModel, Field


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
    supporting_quote: str = Field(
        description=(
            "Short verbatim excerpt from the consultation summary (not the raw transcript) "
            "that justifies this code"
        )
    )
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
