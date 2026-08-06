"""Loads the RAMQ code reference table and narrows it down to candidates for a transcript.

The reference file shipped in this repo is ingested from the official "Manuel des médecins
omnipraticiens — Rémunération à l'acte" — see its "_meta" block for provenance (source
document, ingestion date). Regenerate it via the ramq-ingestion repo's
scripts/ingest_ramq_manual.py rather than hand-editing it.

Scope: family doctors (omnipraticiens) only. Specialist billing codes live in a different
RAMQ manual with different nomenclature and aren't covered here — a specialist table/task
is separate future work, not an extension of this one.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.ramq.vector_retrieval import get_vector_retriever

REFERENCE_PATH = Path(__file__).parent / "reference_data.section_b.json"


class CandidateRetriever(Protocol):
    def candidates_for(self, query: str, limit: int) -> list[str]: ...


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
class PatientTag:
    """Structured eligibility conditions on the patient, extracted from the code's manual
    entry alongside its free-text `rules` — e.g. a visit code that only applies to a
    vulnerable, inscribed patient under 80."""

    age: str | None = None
    vulnerable: bool | None = None
    inscription: str | None = None


@dataclass(frozen=True)
class RamqCode:
    code: str
    description: str
    fees: tuple[FeeVariant, ...] = ()
    unit: str | None = None
    # Free-text billing condition/reference note for this code (e.g. "Ne peut être
    # réclamé avec les codes d'acte relatifs à l'intervention clinique.", or a pointer to a
    # preamble paragraph) — carried verbatim from the manual, one note per code.
    rules: str | None = None
    # Free-text physician-side eligibility condition (e.g. "Clientèle inscrite de moins de
    # 500 patients"), when the code is restricted by something about the billing physician
    # rather than the patient.
    physician: str | None = None
    patient: PatientTag | None = None

    @property
    def price_cad(self) -> float | None:
        """The default/first fee variant's price, for callers that just need one number
        (e.g. a running total). See `fees` for the full context-dependent list."""
        return self.fees[0].price_cad if self.fees else None


def _load_codes(data: dict) -> list[RamqCode]:
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

        patient_data = entry.get("patient")
        patient = (
            PatientTag(
                age=patient_data.get("age"),
                vulnerable=patient_data.get("vulnerable"),
                inscription=patient_data.get("inscription"),
            )
            if patient_data
            else None
        )

        codes.append(
            RamqCode(
                code=entry["code"],
                description=entry["description"],
                fees=fees,
                unit=entry.get("unit"),
                rules=entry.get("rules"),
                physician=entry.get("physician"),
                patient=patient,
            )
        )
    return codes


class RamqReferenceTable:
    def __init__(self, codes: list[RamqCode], vector_retriever: CandidateRetriever | None = None):
        self._codes = codes
        self._by_code = {c.code: c for c in codes}
        self._vector_retriever = vector_retriever

    @classmethod
    def load(cls, path: Path | None = None) -> "RamqReferenceTable":
        # Resolved inside the body (not as a `path: Path = REFERENCE_PATH` default) so
        # that monkeypatching the module-level REFERENCE_PATH in tests actually takes
        # effect — a default argument value is bound once at def time, not per call.
        data = json.loads((path if path is not None else REFERENCE_PATH).read_text())
        return cls(_load_codes(data), vector_retriever=get_vector_retriever())

    def all_codes(self) -> list[RamqCode]:
        return list(self._codes)

    def get(self, code: str) -> RamqCode | None:
        return self._by_code.get(code)

    def candidates_for(self, transcript: str, limit: int = 40) -> list[RamqCode]:
        """Semantic-similarity candidates for a transcript (via the llama_index vector
        retriever), narrowed to a closed set the LLM can choose from instead of relying on
        its own recall of RAMQ codes.

        Returns an empty list when there's no vector retriever configured, or when nothing
        the retriever returns matches a code in this table — a random slice isn't a
        meaningful fallback, and the model is instructed to return an empty codes list
        rather than guess from an empty/irrelevant candidate set.
        """
        if self._vector_retriever is None:
            return []
        codes = self._vector_retriever.candidates_for(transcript, limit)
        return self._codes_for(codes)

    def _codes_for(self, codes: list[str]) -> list[RamqCode]:
        """Maps ranked code strings to RamqCode, preserving rank order and deduplicating.
        A code the retriever returns but that's absent from this table (corpus drift
        between the vector index and reference_data.section_b.json — e.g. the vector
        index's few psychiatric-exam codes that don't exist in the current reference
        table) is silently dropped rather than raising, since there's no price/eligibility
        data to enrich it with anyway.
        """
        seen: set[str] = set()
        result: list[RamqCode] = []
        for code in codes:
            if code in seen:
                continue
            seen.add(code)
            entry = self._by_code.get(code)
            if entry is not None:
                result.append(entry)
        return result


@lru_cache(maxsize=1)
def get_reference_table() -> RamqReferenceTable:
    return RamqReferenceTable.load()
