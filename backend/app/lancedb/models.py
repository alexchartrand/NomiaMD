from pydantic import BaseModel

class CodeRowFee(BaseModel):
    amount: float | None = None
    amount_text: str | None = None
    context: str | None = None
    lieu: str | None = None
    majoration: str | None = None


class CodeRow(BaseModel):
    """A raw row from the `codes` LanceDB table, validated at the point it crosses into this
    backend — a projection of ramq-ingestion's src/embedding/codes_embedding/
    code_table_schema.py, selecting only the columns the read side actually uses (mirrors
    DocumentRow's own vector/header_path/lexical_terms/expansion_terms/needs_review/
    review_reason omission below: those exist for MultiMatchQuery to search over, not for the
    app to consume). Kept separate from Code (app/ramq_codes/models.py), this backend's own
    internal shape built from a validated CodeRow."""

    number: str
    libelle: str
    description: str
    when_to_use: list[str] = []
    rules: list[str] = []
    fees: list[CodeRowFee] = []


class DocumentRow(BaseModel):
    """A raw row from the `documents-embeddings` LanceDB table, validated at the point it
    crosses into this backend — a projection of ramq-ingestion's
    src/embedding/documents_embedding/document_table_schema.py, selecting only the columns
    the read side actually uses. Deliberately omits `vector`: DocumentRepository always
    `.select()`s this row's columns explicitly, so the ~4KB embedding never crosses the wire
    for a hit that's about to be converted to a TextNode and thrown away."""

    id: str
    text: str
    title: str
    section_number: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_references: list[str] | None = None
    code_references: list[str] | None = None