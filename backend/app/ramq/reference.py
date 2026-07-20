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

# Precomputed corpus embeddings from the ramq-ingestion repo — one entry per manual table
# row (a code can have more than one row, e.g. distinct fee-variant sub-rows), each carrying
# its own embedding vector so this repo never has to re-embed the reference table itself.
EMBEDDINGS_PATH = Path(__file__).parent / "ramq_embeddings_section_b.jsonl"


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


@dataclass(frozen=True)
class EmbeddedChunk:
    """One embedded row from ramq-ingestion's embeddings export. A "chunk" is a manual table
    row, not a code — a code can have more than one row (e.g. distinct fee-variant sub-rows),
    so more than one chunk can share the same `code`. `text` is ingestion's own synthesized
    embedding input (breadcrumb + code + description + price rows); this repo doesn't
    re-derive it and doesn't need it beyond debugging, since `embedding` is already computed.
    `breadcrumb` is the manual's own table-of-contents path down to this row (e.g. ["B -
    Consultation, examen et visite", "Visites sur rendez-vous (patient de moins de 80 ans)",
    ...]) — used to keep any one manual subsection from crowding out the rest of a candidate
    list, see RamqReferenceTable._apply_cluster_cap."""

    code: str
    text: str
    embedding: tuple[float, ...]
    embedding_model: str
    breadcrumb: tuple[str, ...]


def _load_embedded_chunks(path: Path) -> list[EmbeddedChunk]:
    chunks = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        chunks.append(
            EmbeddedChunk(
                code=row["code"],
                text=row["text"],
                embedding=tuple(row["embedding"]),
                embedding_model=row["embedding_model"],
                breadcrumb=tuple(row.get("breadcrumb") or ()),
            )
        )
    return chunks


class RamqReferenceTable:
    def __init__(self, codes: list[RamqCode], embedded_chunks: list[EmbeddedChunk] | None = None):
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
        self._embedding_retriever: EmbeddingRetriever | None = None
        self._embedding_corpus_size = 0
        if embeddings_enabled():
            if embedded_chunks:
                # Corpus vectors are precomputed by ramq-ingestion — only the query needs a
                # live call, and it must land in the same vector space as the shipped
                # corpus, so the model is pinned to whatever the chunks themselves recorded
                # rather than trusting NOMIAMD_EMBEDDING_MODEL to happen to agree.
                model = embedded_chunks[0].embedding_model
                self._embedding_retriever = EmbeddingRetriever(
                    embedded_chunks,
                    embed_fn=lambda texts: embed_texts(texts, model=model),
                    vectors=[c.embedding for c in embedded_chunks],
                )
                self._embedding_corpus_size = len(embedded_chunks)
            else:
                # No precomputed corpus available (e.g. a small hand-built table in tests) —
                # fall back to embedding RamqCode text live, as before.
                self._embedding_retriever = EmbeddingRetriever(codes, text_for=text_for, embed_fn=embed_texts)
                self._embedding_corpus_size = len(codes)

        # Maps code -> its manual subsection (breadcrumb, truncated to the top 2 levels —
        # deep enough to separate unrelated subsections like "Consultation en éthique
        # clinique" from "Visites sur rendez-vous", shallow enough that most legitimately
        # related variants of one scenario still share a bucket), used by
        # _apply_cluster_cap to keep one subsection from crowding out the rest of a
        # candidate list. Empty (no capping) when there's no breadcrumb data on hand, e.g.
        # embeddings are disabled or this table was hand-built without embedded_chunks.
        self._code_cluster: dict[str, tuple[str, ...]] = {}
        if embedded_chunks:
            for chunk in embedded_chunks:
                self._code_cluster.setdefault(chunk.code, chunk.breadcrumb[:2])

    @classmethod
    def load(cls, path: Path | None = None, embeddings_path: Path | None = None) -> "RamqReferenceTable":
        # Resolved inside the body (not as a `path: Path = REFERENCE_PATH` default) so
        # that monkeypatching the module-level REFERENCE_PATH in tests actually takes
        # effect — a default argument value is bound once at def time, not per call.
        data = json.loads((path if path is not None else REFERENCE_PATH).read_text())

        embedded_chunks = None
        if embeddings_enabled():
            # Gated on embeddings_enabled() to skip parsing a ~1024-dim-per-row file when
            # semantic retrieval is off anyway.
            resolved_embeddings_path = embeddings_path if embeddings_path is not None else EMBEDDINGS_PATH
            if resolved_embeddings_path.exists():
                embedded_chunks = _load_embedded_chunks(resolved_embeddings_path)

        return cls(_load_codes(data), embedded_chunks=embedded_chunks)

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

        When breadcrumb data is available (precomputed embeddings path), the fused ranking
        is additionally capped per manual subsection before truncating to `limit` — BM25's
        degeneracy above means several codes from a subsection with zero real relevance
        (e.g. geriatric exams, ethics consultations, medico-legal forms) routinely pick up
        just enough incidental score to occupy several of the `limit` slots each, at a real
        note's length. Left unchecked, that crowds out — or at minimum buries — the one
        subsection actually worth showing the model, and has been observed to make the model
        bail out to an empty result even when a correct candidate was technically present in
        the list (see _apply_cluster_cap).
        """
        total = len(self._codes)
        bm25_ranked = self._retriever.candidates_for(transcript, total)
        if self._embedding_retriever is None:
            return bm25_ranked[:limit]

        # Ranked over the embedding retriever's own corpus size, not `total`: when embeddings
        # come from the precomputed chunks file, that corpus is rows (possibly more than one
        # per code), not codes, so it can be a different size than self._codes.
        emb_ranked_raw = self._embedding_retriever.candidates_for(transcript, self._embedding_corpus_size)
        emb_ranked = self._dedup_to_codes(emb_ranked_raw)

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
        capped_codes = self._apply_cluster_cap(ranked_codes, limit)
        return [by_code[code] for code in capped_codes]

    # Max candidates from any one manual subsection (breadcrumb[:2]) in a fused candidate
    # list — see the "breadcrumb data is available" note in candidates_for's docstring.
    _CLUSTER_CAP = 6

    def _apply_cluster_cap(self, ranked_codes: list[str], limit: int) -> list[str]:
        """Walks `ranked_codes` (already RRF-sorted, best first) and keeps at most
        `_CLUSTER_CAP` per manual subsection, deferring the rest to a backfill pass so the
        result still reaches `limit` if capping alone doesn't produce enough. A no-op
        (plain top-`limit` slice) when there's no cluster data — e.g. BM25-only mode, or a
        hand-built table with no embedded_chunks.
        """
        if not self._code_cluster:
            return ranked_codes[:limit]

        cluster_counts: dict[tuple[str, ...], int] = {}
        kept: list[str] = []
        overflow: list[str] = []
        for code in ranked_codes:
            cluster = self._code_cluster.get(code)
            if cluster is None or cluster_counts.get(cluster, 0) < self._CLUSTER_CAP:
                if cluster is not None:
                    cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
                kept.append(code)
            else:
                overflow.append(code)
            if len(kept) >= limit:
                break

        if len(kept) < limit:
            kept.extend(overflow[: limit - len(kept)])
        return kept[:limit]

    def _dedup_to_codes(self, ranked: list) -> list[RamqCode]:
        """Maps a ranked list of RamqCode or EmbeddedChunk items (both expose `.code`) down
        to deduplicated RamqCodes in rank order, keeping only each code's first (best-ranked)
        occurrence. Needed because the precomputed-chunks corpus can have more than one row
        per code (e.g. distinct fee-variant sub-rows), and because a chunk's code might not
        exist in the current reference table (the two files are generated independently and
        can drift) — such chunks are silently dropped rather than raising.
        """
        seen: set[str] = set()
        result = []
        for item in ranked:
            if item.code in seen:
                continue
            seen.add(item.code)
            code_obj = self._by_code.get(item.code)
            if code_obj is not None:
                result.append(code_obj)
        return result


@lru_cache(maxsize=1)
def get_reference_table() -> RamqReferenceTable:
    return RamqReferenceTable.load()
