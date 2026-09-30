from typing import Literal

from pydantic import BaseModel, field_validator

FeeUnit = Literal["dollars", "unités"]


class CodeRowFee(BaseModel):
    amount: float | None = None
    amount_text: str | None = None
    # The manual's role column (R = 1, R = 2, R = 7...), null for a single-amount table. Its
    # meaning is section-specific (radiology's R = 7 is the laboratory fee), so it's kept raw
    # rather than mapped to one meaning per number.
    role: int | None = None
    # `amount` counts anesthesia base units, not dollars, when this is "unités" (typically
    # R = 2). Never bill such an amount as dollars — see app/claims/fees.py's FeeSnapshotter.
    unit: FeeUnit = "dollars"
    context: str | None = None
    lieux: list[str] = []
    majoration: str | None = None

    @field_validator("lieux", mode="before")
    @classmethod
    def _null_lieux_as_empty(cls, value):
        return [] if value is None else value

    @field_validator("unit", mode="before")
    @classmethod
    def _null_unit_as_dollars(cls, value):
        return "dollars" if value is None else value


class CodeRow(BaseModel):
    """A raw row from the current `codes_<rev>` LanceDB table (see code_versions.py), validated
    at the point it crosses into this backend — a projection of ramq-ingestion's
    src/ramq_ingestion/codes/storage/code_table_schema.py, selecting only the columns the read
    side actually uses (lexical_terms/expansion_terms exist for MultiMatchQuery to search
    over; needs_review/review_reason aren't consumed yet — see BACKLOG.md). Kept separate from
    Code (app/ramq_codes/models.py), this backend's own internal shape built from a validated
    CodeRow."""

    number: str
    description: str
    # The manual's own taxonomy path, e.g. "B — Consultation, examen et visite > Visites sur
    # rendez-vous (patient de moins de 80 ans) > Patient non vulnérable inscrit > Visite de
    # prise en charge". Goes into the billing prompt verbatim, so the model can see what
    # distinguishes one candidate from a near-identical sibling.
    header_path: str
    when_to_use: list[str] = []
    rules: list[str] = []
    fees: list[CodeRowFee] = []
    # Eligibility axes, typed by ramq-ingestion from the same qualifiers the description
    # spells out in prose. Every bound is inclusive and in whole units ("moins de 80 ans" is
    # max_age=79); null always means "no restriction on this axis", never "unknown" — see
    # app/lancedb/eligibility.py, which filters on them.
    min_age: int | None = None
    max_age: int | None = None
    min_panel_size: int | None = None
    max_panel_size: int | None = None
    requires_registered: bool | None = None
    requires_vulnerable: bool | None = None


class CodeVersionRow(BaseModel):
    """A row of ramq-ingestion's `code_versions` registry: one promoted `codes_<rev>` table.
    Exactly one row has is_current=True — the table this backend retrieves from (see
    code_versions.py). The others point at older manual revisions."""

    manual_rev: str
    table_name: str
    is_current: bool
    promoted_at: str
    code_count: int


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
    # The source document's own URL (e.g. the RAMQ manual page/PDF this chunk was cut from)
    # — propagated into citation metadata so the model can cite a real link, not just a
    # section/page label (see engine.py's _citation_prefix).
    url: str
    section_number: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_references: list[str] | None = None
    code_references: list[str] | None = None