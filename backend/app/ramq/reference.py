"""Loads the RAMQ code reference table and narrows it down to candidates for a transcript.

The reference file shipped in this repo (reference_data.json) is ingested from the official
"Manuel des médecins omnipraticiens — Rémunération à l'acte" — see reference_data.json's
"_meta" block for provenance (source document, ingestion date). Regenerate it via
scripts/ingest_ramq_manual.py rather than hand-editing it.

Scope: family doctors (omnipraticiens) only. Specialist billing codes live in a different
RAMQ manual with different nomenclature and aren't covered here — a specialist table/task
is separate future work, not an extension of this one.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.ramq.retrieval import BM25Retriever

REFERENCE_PATH = Path(__file__).parent / "reference_data.json"


@dataclass(frozen=True)
class FeeVariant:
    """One billed amount for a code, tied to the practice context it applies in.

    Most real RAMQ codes have more than one price — e.g. a visit code is billed differently
    "en cabinet ou à domicile" vs. "en CLSC ou en GMF-U". Both are kept rather than
    flattened to a single number, since discarding one would produce wrong totals for a
    meaningful fraction of encounters.
    """

    context_label: str
    price_cad: float | None = None
    # Set instead of price_cad for "majoration" codes — time-of-day/weekend surcharges
    # billed as a percentage of a base code's fee rather than a flat dollar amount.
    percentage: float | None = None


@dataclass(frozen=True)
class RamqCode:
    code: str
    description: str
    category: str
    keywords: tuple[str, ...] = ()
    fees: tuple[FeeVariant, ...] = ()
    unit: str | None = None
    source_ref: str | None = None
    # Empty in Phase 1 — populated once rule-text retrieval (rules.py) lands, without a
    # schema migration on this dataclass.
    rule_ids: tuple[str, ...] = ()
    # Set by ingestion when the automated parser was uncertain about this entry (e.g. a
    # description/price line-count mismatch, or a heuristic-resolved header ambiguity —
    # see ingest/parse_html.py). Not re-verified by anything at runtime; it's a signal for
    # future manual cleanup, not a gate on whether the code is usable.
    needs_review: bool = False

    @property
    def price_cad(self) -> float | None:
        """The default/first fee variant's price, for callers that just need one number
        (e.g. a running total). See `fees` for the full context-dependent list."""
        return self.fees[0].price_cad if self.fees else None


def _load_codes(path: Path) -> list[RamqCode]:
    data = json.loads(path.read_text())
    codes = []
    for entry in data["codes"]:
        if "fees" in entry:
            fees = tuple(
                FeeVariant(
                    context_label=fee.get("context_label", ""),
                    price_cad=fee.get("price_cad"),
                    percentage=fee.get("percentage"),
                )
                for fee in entry["fees"]
            )
        elif entry.get("price_cad") is not None:
            # Legacy shape (single flat price_cad, no context) — wrap into one variant so
            # older fixtures/placeholder data keep loading during the migration.
            fees = (FeeVariant(context_label="", price_cad=entry["price_cad"]),)
        else:
            fees = ()

        codes.append(
            RamqCode(
                code=entry["code"],
                description=entry["description"],
                category=entry["category"],
                keywords=tuple(entry.get("keywords", [])),
                fees=fees,
                unit=entry.get("unit"),
                source_ref=entry.get("source_ref"),
                rule_ids=tuple(entry.get("rule_ids", [])),
                needs_review=entry.get("needs_review", False),
            )
        )
    return codes


class RamqReferenceTable:
    def __init__(self, codes: list[RamqCode]):
        self._codes = codes
        self._by_code = {c.code: c for c in codes}
        self._retriever = BM25Retriever(
            codes,
            # Many real descriptions are terse fragments ("sous anesthésie locale") that
            # only make sense read alongside their table section — folding category into
            # the indexed text lets a query like "douleur thoracique" also match codes
            # filed under "Cardiologie et angiologie" even without the word "thoracique"
            # in the description itself.
            text_for=lambda c: f"{c.description} {c.category} {' '.join(c.keywords)}",
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "RamqReferenceTable":
        # Resolved inside the body (not as a `path: Path = REFERENCE_PATH` default) so
        # that monkeypatching the module-level REFERENCE_PATH in tests actually takes
        # effect — a default argument value is bound once at def time, not per call.
        return cls(_load_codes(path if path is not None else REFERENCE_PATH))

    def all_codes(self) -> list[RamqCode]:
        return list(self._codes)

    def get(self, code: str) -> RamqCode | None:
        return self._by_code.get(code)

    def candidates_for(self, transcript: str, limit: int = 25) -> list[RamqCode]:
        """BM25-ranked candidates for a transcript, narrowed to a closed set the LLM can
        choose from instead of relying on its own recall of RAMQ codes.

        Returns an empty list rather than an arbitrary slice of the table when nothing
        scores above zero — at thousands of entries, a random slice isn't a meaningful
        fallback, and the model is instructed to return an empty codes list rather than
        guess from an empty/irrelevant candidate set.
        """
        return self._retriever.candidates_for(transcript, limit)


@lru_cache(maxsize=1)
def get_reference_table() -> RamqReferenceTable:
    return RamqReferenceTable.load()
