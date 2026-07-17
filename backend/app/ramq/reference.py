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

from app.ramq.embeddings import embed_texts, embeddings_enabled
from app.ramq.retrieval import BM25Retriever, EmbeddingRetriever

REFERENCE_PATH = Path(__file__).parent / "reference_data.section_b.json"


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
    def __init__(self, codes: list[RamqCode]):
        self._codes = codes
        self._by_code = {c.code: c for c in codes}

        def text_for(c: RamqCode) -> str:
            # Many real descriptions are terse fragments ("sous anesthésie locale") that
            # only make sense read alongside their table section — folding category into
            # the indexed text lets a query like "douleur thoracique" also match codes
            # filed under "Cardiologie et angiologie" even without the word "thoracique"
            # in the description itself. The code's rules/physician/patient eligibility
            # text is folded in too (embeddings only — BM25 leaves it out, see its class
            # docstring on why lexical matching doesn't help here) so a code's real
            # eligibility nuance is part of what a semantic search matches against, not
            # just its terse label.
            base = f"{c.description}"
            extra = [c.rules, c.physician]
            if c.patient is not None:
                extra += [c.patient.age, c.patient.inscription]
                if c.patient.vulnerable:
                    extra.append("patient vulnérable")
            extra_text = " ".join(part for part in extra if part)
            return f"{base} {extra_text}".strip()

        # BM25 stays on the plain description+category+keywords text (rule/eligibility text
        # is administrative language that rarely overlaps lexically with a clinical
        # transcript — see EmbeddingRetriever's docstring); the semantic retriever below
        # is where folding it into the indexed text actually helps.
        self._retriever = BM25Retriever(
            codes,
            text_for=lambda c: f"{c.description}",
        )
        self._embedding_retriever: EmbeddingRetriever[RamqCode] | None = None
        if embeddings_enabled():
            self._embedding_retriever = EmbeddingRetriever(codes, text_for=text_for, embed_fn=embed_texts)

    @classmethod
    def load(cls, path: Path | None = None) -> "RamqReferenceTable":
        # Resolved inside the body (not as a `path: Path = REFERENCE_PATH` default) so
        # that monkeypatching the module-level REFERENCE_PATH in tests actually takes
        # effect — a default argument value is bound once at def time, not per call.
        data = json.loads((path if path is not None else REFERENCE_PATH).read_text())
        return cls(_load_codes(data))

    def all_codes(self) -> list[RamqCode]:
        return list(self._codes)

    def get(self, code: str) -> RamqCode | None:
        return self._by_code.get(code)

    def candidates_for(self, transcript: str, limit: int = 40) -> list[RamqCode]:
        """BM25-ranked (plus semantic, when embeddings are configured) candidates for a
        transcript, narrowed to a closed set the LLM can choose from instead of relying on
        its own recall of RAMQ codes.

        Returns an empty list rather than an arbitrary slice of the table when nothing
        scores above zero — at thousands of entries, a random slice isn't a meaningful
        fallback, and the model is instructed to return an empty codes list rather than
        guess from an empty/irrelevant candidate set.

        When embeddings are configured, results are fused via Reciprocal Rank Fusion (RRF)
        over each retriever's *full* ranking, not a union of their independently-truncated
        top-`limit` lists. That distinction matters in practice: a real (long, detail-heavy)
        clinical note tokenizes into a large bag of terms, and at this table's current size
        (a few hundred codes) BM25 degenerates — nearly every code picks up some nonzero
        score from incidental vocabulary overlap (lab values, med names, clinic/admin
        boilerplate), so the *correct* code can rank outside the top `limit` on lexical
        grounds alone even though it's a clear semantic match. Fusing full rankings by
        reciprocal rank lets a candidate that both retrievers rank moderately well (say,
        top 50 lexically, top 30 semantically) outscore one either retriever ranks highly in
        isolation but the other doesn't corroborate at all — see
        test_ramq_reference.py for the regression case this fixes.
        """
        total = len(self._codes)
        bm25_ranked = self._retriever.candidates_for(transcript, total)
        if self._embedding_retriever is None:
            return bm25_ranked[:limit]

        emb_ranked = self._embedding_retriever.candidates_for(transcript, total)

        # Standard RRF constant (Cormack et al.) — large enough that a single retriever's
        # #1 pick doesn't automatically dominate a code both retrievers rank moderately.
        RRF_K = 60
        by_code = {c.code: c for c in bm25_ranked}
        scores: dict[str, float] = {}
        for rank, c in enumerate(bm25_ranked):
            scores[c.code] = scores.get(c.code, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, c in enumerate(emb_ranked):
            by_code.setdefault(c.code, c)
            scores[c.code] = scores.get(c.code, 0.0) + 1.0 / (RRF_K + rank + 1)

        ranked_codes = sorted(scores, key=lambda code: scores[code], reverse=True)
        return [by_code[code] for code in ranked_codes[:limit]]


@lru_cache(maxsize=1)
def get_reference_table() -> RamqReferenceTable:
    return RamqReferenceTable.load()
