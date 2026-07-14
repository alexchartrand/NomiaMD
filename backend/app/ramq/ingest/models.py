"""Format-agnostic intermediate representation for a parsed RAMQ manual, sitting between
the raw HTML/PDF parsers and the reviewed, promoted reference_data.json.
"""

from dataclasses import dataclass, field


@dataclass
class RawFeeVariant:
    context_label: str
    price_cad: float | None = None
    percentage: float | None = None


@dataclass
class RawCodeRow:
    code: str
    description: str
    category: str
    fees: list[RawFeeVariant] = field(default_factory=list)
    unit: str | None = None
    source_ref: str | None = None
    # Raw text of the row, kept for traceability during human review — not carried into
    # the promoted reference_data.json.
    raw_row_text: str = ""
    # Set when the parser couldn't cleanly pair description sub-lines with price sub-lines
    # (mismatched counts) — flags the row for a closer look during review rather than
    # silently guessing.
    needs_review: bool = False
