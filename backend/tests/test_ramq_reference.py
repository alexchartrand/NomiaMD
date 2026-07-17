"""Unit tests for RamqReferenceTable/candidates_for in isolation, against small synthetic
tables — no dependency on the real (large, frequently-regenerated) reference_data.json.

BM25's classic IDF formula is degenerate at very small corpus sizes (e.g. with 2 documents,
a term appearing in exactly 1 of them scores idf=log(1)=0) — these fixtures use a handful
of diverse entries rather than 1-2, so scores behave the way they will at real (thousands
of entries) scale.
"""

from app.ramq.reference import FeeVariant, RamqCode, RamqReferenceTable
from app.ramq.retrieval import tokenize


def _diverse_table() -> RamqReferenceTable:
    return RamqReferenceTable(
        [
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
    )


def test_candidates_ranked_by_relevance():
    table = _diverse_table()
    results = table.candidates_for("Patient suivi pour diabète de type 2, glycémies élevées")
    assert results[0].code == "DIABETE"


def test_candidates_for_respects_limit():
    table = _diverse_table()
    results = table.candidates_for("douleur thoracique, hypertension, diabète, plaie", limit=2)
    assert len(results) == 2


def test_candidates_for_no_match_returns_empty():
    table = _diverse_table()
    # At real-world scale (thousands of entries), an arbitrary fallback slice isn't a
    # meaningful candidate list — an empty result is what tells billing_codes.py's system
    # prompt to have the model return an empty codes list rather than guess.
    assert table.candidates_for("astronomie et voyages spatiaux") == []


def test_candidates_for_is_accent_and_case_insensitive():
    table = _diverse_table()
    # Transcript typed without accents (copy-paste artifact) should still match.
    with_accents = table.candidates_for("hypertension artérielle chez le patient")
    without_accents = table.candidates_for("HYPERTENSION arterielle chez le patient")
    assert with_accents and with_accents[0].code == "HTA"
    assert without_accents and without_accents[0].code == "HTA"


def test_tokenize_drops_french_stopwords():
    assert "non" not in tokenize("cible non atteinte")
    assert "de" not in tokenize("bilan de contrôle")


def test_tokenize_stems_plural_and_singular_to_the_same_root():
    # A transcript saying "plaie" (singular) must be able to match a code description that
    # only ever says "plaies" (plural) — without stemming these are unrelated tokens and a
    # correct candidate can be permanently unretrievable regardless of query wording.
    assert tokenize("une plaie") == tokenize("des plaies")


def test_tokenize_strips_citation_boilerplate():
    # "(P.C. 13)", "(P.G. 2.2.9 A)" etc. are the manual's internal section cross-references,
    # not clinical content — left in, they tokenize into single letters/bare digits that
    # spuriously "match" any other entry citing the same section.
    assert tokenize("Réparation de plaies (P.C. 13)") == tokenize("Réparation de plaies")
    assert tokenize("Examen d'urgence (P.G. 2.2.9 A)") == tokenize("Examen d'urgence")


def test_candidates_for_finds_code_only_described_in_plural():
    # Small corpus per this file's module docstring caveat about BM25 IDF degeneracy at
    # tiny N — reuse the diverse table's unrelated filler entries (skipping its "SUTURE"
    # entry, which already says "plaie" singular and would confound what this test is
    # isolating: whether a plural-only description is still retrievable).
    filler = [c for c in _diverse_table().all_codes() if c.code != "SUTURE"]
    wound_code = RamqCode(
        code="WOUND",
        description="Réparation de plaies (débridement compris), moins de deux centimètres et demi (2,5 cm)",
    )
    table = RamqReferenceTable([*filler, wound_code])
    results = table.candidates_for("Plaie de 2 cm à la paume, suturée sous anesthésie locale")
    assert results and results[0].code == "WOUND"


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


def test_candidates_for_stays_bm25_only_without_embeddings_enabled(monkeypatch):
    import app.ramq.reference as reference_module

    calls = []
    monkeypatch.setattr(reference_module, "embed_texts", lambda texts: calls.append(texts) or [])
    # embeddings_enabled() is False by default (no OPENAI_API_KEY) — constructing a table
    # must not call embed_texts at all, so existing BM25-only behavior is unaffected.
    _diverse_table()
    assert calls == []


def test_candidates_for_merges_embedding_hits_bm25_alone_would_miss(monkeypatch):
    """A transcript phrased with zero vocabulary overlap against a code's own text can
    never surface via BM25 (lexical, term-overlap only) — this is exactly the gap
    EmbeddingRetriever exists to close. Uses a fake embed_fn (no real API call) that
    considers the query and one code semantically close despite sharing no words."""
    import app.ramq.reference as reference_module

    monkeypatch.setattr(reference_module, "embeddings_enabled", lambda: True)

    query = "défense abdominale mystère"

    def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        # Pretends code A's real description and this unrelated-vocabulary query are
        # semantically close — a stand-in for what a real embedding model would do with
        # true synonyms/paraphrases, which BM25's term-overlap can never see.
        return [
            [1.0, 0.0] if ("lacération" in t.lower() or t == query) else [0.0, 1.0]
            for t in texts
        ]

    monkeypatch.setattr(reference_module, "embed_texts", fake_embed_texts)

    codes = [
        RamqCode(code="A", description="Une lacération profonde de la main"),
        RamqCode(code="B", description="Suivi de tension artérielle"),
    ]
    table = RamqReferenceTable(codes)

    assert table._retriever.candidates_for(query, 25) == []  # confirms BM25 alone finds nothing

    results = table.candidates_for(query)
    assert any(c.code == "A" for c in results)
