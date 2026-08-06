from pydantic import BaseModel, Field


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


class BillingCodesResult(BaseModel):
    codes: list[ExtractedCode]
    notes: str | None = Field(
        default=None,
        description="Anything the model flagged as ambiguous or needing physician review",
    )
