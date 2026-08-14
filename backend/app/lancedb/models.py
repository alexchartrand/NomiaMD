from pydantic import BaseModel

class CodeRowFee(BaseModel):
    amount: float | None = None
    when_to_use: str | None = None
    majoration: str | None = None


class CodeRow(BaseModel):
    """A raw row from the `codes` LanceDB table, validated at the point it crosses into this
    backend — mirrors ramq-ingestion's src/embedding/code_table_schema.py column-for-column,
    which is itself written from that repo's Code/Fee (src/models.py). Kept separate from
    RamqCandidate, which is this backend's own internal shape built from a validated CodeRow."""

    number: str
    description: str
    when_to_use: list[str] = []
    rules: list[str] = []
    fees: list[CodeRowFee] = []
    confidence: float