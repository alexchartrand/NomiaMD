"""Unit tests for RamqReferenceTable against small synthetic tables.

Candidate ranking itself is llama_index's job (see test_vector_retrieval.py) — these tests
only cover what RamqReferenceTable does with a retriever's output: passing rank order
through, respecting `limit`, and mapping ranked code strings back to RamqCode (including
the corpus-drift case where a retriever returns a code this table doesn't have).
"""

from app.ramq.reference import FeeVariant, RamqCode, RamqReferenceTable


class _StubRetriever:
    """Always returns the same ranked code list regardless of query — stands in for the
    real llama_index-backed retriever so these tests don't need a real index or network
    call."""

    def __init__(self, codes: list[str]):
        self._codes = codes

    def candidates_for(self, query: str, limit: int) -> list[str]:
        return self._codes[:limit]


def _diverse_table(retriever_codes: list[str] | None = None) -> RamqReferenceTable:
    codes = [
        RamqCode(code="DIABETE", description="Suivi de diabète de type 2"),
        RamqCode(code="HTA", description="Prise en charge de l'hypertension artérielle"),
        RamqCode(code="SUTURE", description="Suture d'une plaie à la main sous anesthésie locale"),
        RamqCode(
            code="APPENDICE",
            description="Consultation pour douleur abdominale, suspicion d'appendicite",
        ),
        RamqCode(
            code="STEMI",
            description="Prise en charge d'un infarctus aigu du myocarde (STEMI)",
        ),
        RamqCode(code="PSY", description="Évaluation d'une symptomatologie dépressive"),
    ]
    default_ranking = retriever_codes if retriever_codes is not None else [c.code for c in codes]
    return RamqReferenceTable(codes, vector_retriever=_StubRetriever(default_ranking))


def test_candidates_for_passes_through_retriever_rank_order():
    table = _diverse_table(["STEMI", "DIABETE", "HTA"])
    results = table.candidates_for("peu importe le texte de la requête")
    assert [c.code for c in results] == ["STEMI", "DIABETE", "HTA"]


def test_candidates_for_respects_limit():
    table = _diverse_table(["DIABETE", "HTA", "SUTURE", "APPENDICE"])
    results = table.candidates_for("peu importe", limit=2)
    assert [c.code for c in results] == ["DIABETE", "HTA"]


def test_candidates_for_no_vector_retriever_returns_empty():
    table = RamqReferenceTable([RamqCode(code="A", description="x")], vector_retriever=None)
    assert table.candidates_for("peu importe") == []


def test_candidates_for_drops_codes_the_retriever_returns_but_table_lacks():
    # Corpus drift: the vector index and reference_data.section_b.json are independently
    # maintained and can disagree on which codes exist — a retriever hit with no matching
    # RamqCode must be silently dropped, not raised, since there's no price/eligibility
    # data to enrich it with anyway.
    table = _diverse_table(["DIABETE", "GHOST-CODE", "HTA"])
    results = table.candidates_for("peu importe")
    assert [c.code for c in results] == ["DIABETE", "HTA"]


def test_candidates_for_deduplicates_repeated_codes():
    table = _diverse_table(["DIABETE", "DIABETE", "HTA"])
    results = table.candidates_for("peu importe")
    assert [c.code for c in results] == ["DIABETE", "HTA"]


def test_ramq_code_price_cad_uses_first_fee_variant():
    code = RamqCode(
        code="A",
        description="Visite de suivi",
        fees=(
            FeeVariant(context_label="en cabinet", price_cad=42.85),
            FeeVariant(context_label="en CLSC", price_cad=32.25),
        ),
    )
    assert code.price_cad == 42.85


def test_ramq_code_price_cad_none_for_majoration_only():
    code = RamqCode(
        code="A",
        description="Majoration de nuit",
        unit="majoration %",
        fees=(FeeVariant(context_label="0h-8h", percentage=101.0),),
    )
    assert code.price_cad is None


def test_get_and_all_codes():
    table = _diverse_table()
    assert table.get("HTA").code == "HTA"
    assert table.get("missing") is None
    assert len(table.all_codes()) == 6
