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
            RamqCode(
                code="DIABETE",
                description="Suivi de diabète de type 2",
                category="chronic_disease_management",
                keywords=("diabète", "glycémie", "hba1c"),
            ),
            RamqCode(
                code="HTA",
                description="Prise en charge de l'hypertension artérielle",
                category="chronic_disease_management",
                keywords=("hypertension", "tension artérielle"),
            ),
            RamqCode(
                code="SUTURE",
                description="Suture d'une plaie à la main sous anesthésie locale",
                category="procedure",
                keywords=("suture", "plaie", "anesthésie locale"),
            ),
            RamqCode(
                code="APPENDICE",
                description="Consultation pour douleur abdominale, suspicion d'appendicite",
                category="urgence",
                keywords=("douleur abdominale", "appendicite"),
            ),
            RamqCode(
                code="STEMI",
                description="Prise en charge d'un infarctus aigu du myocarde (STEMI)",
                category="cardiologie",
                keywords=("infarctus", "stemi", "douleur thoracique"),
            ),
            RamqCode(
                code="PSY",
                description="Évaluation d'une symptomatologie dépressive",
                category="santé mentale",
                keywords=("dépression", "phq-9"),
            ),
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
        description="moins de deux centimètres et demi (2,5 cm)",
        category="Réparation de plaies (débridement compris)",
    )
    table = RamqReferenceTable([*filler, wound_code])
    results = table.candidates_for("Plaie de 2 cm à la paume, suturée sous anesthésie locale")
    assert results and results[0].code == "WOUND"


def test_ramq_code_price_cad_uses_first_fee_variant():
    code = RamqCode(
        code="A",
        description="Visite de suivi",
        category="c",
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
        category="c",
        unit="majoration %",
        fees=(FeeVariant(context_label="0h-8h", percentage=101.0),),
    )
    assert code.price_cad is None


def test_get_and_all_codes():
    table = _diverse_table()
    assert table.get("HTA").code == "HTA"
    assert table.get("missing") is None
    assert len(table.all_codes()) == 6
