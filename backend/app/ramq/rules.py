"""Condition/exclusion/eligibility notes attached to RAMQ codes — the "AVIS :" narrative
text ingested from the manual's PDF export (see ramq-ingestion's parse_pdf.py for why the
PDF, not the HTML, is the source for this). A bare code + description + price doesn't
capture that a code can't be billed alongside another, or only applies under a specific
patient/context condition; this is where that text lives once ingested.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RamqRuleChunk:
    id: str
    text: str
    code_ids: tuple[str, ...] = ()
    section_label: str = ""
    source_ref: str | None = None
    # Set when the code_ids link was a heuristic guess at ingestion (e.g. a section-level
    # note not yet matched to specific codes by human review) rather than the manual's own
    # explicit "voir les codes de facturation X, Y" statement — same meaning as RamqCode's
    # needs_review, just for the rule's code linkage specifically.
    needs_review: bool = False


def load_rules(data: dict) -> list[RamqRuleChunk]:
    rules = []
    for entry in data.get("rules", []):
        rules.append(
            RamqRuleChunk(
                id=entry["id"],
                text=entry["text"],
                code_ids=tuple(entry.get("code_ids", [])),
                section_label=entry.get("section_label", ""),
                source_ref=entry.get("source_ref"),
                needs_review=entry.get("needs_review", False),
            )
        )
    return rules
