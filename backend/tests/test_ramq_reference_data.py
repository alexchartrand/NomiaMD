"""Exercises the real reference_data.json fixture at the repo root of app/ramq/ — no
mocking needed, this is pure file parsing. Mirrors test_sample_patients.py's pattern for
"parses the real committed fixture" regression coverage.

Does NOT use the small_reference_table fixture from conftest.py (that's for tests that
should stay decoupled from the real data's size/content) — this test's whole point is to
check the real, promoted file."""

import json

from app.ramq.reference import EMBEDDINGS_PATH, REFERENCE_PATH, RamqReferenceTable, _load_embedded_chunks


def test_real_reference_data_parses():
    table = RamqReferenceTable.load(REFERENCE_PATH)
    codes = table.all_codes()
    # Currently a section-B-only ingestion run (~310 codes); a generous, stable-ish floor
    # for that, not the full ~4,000-code manual.
    assert len(codes) > 100
    assert len({c.code for c in codes}) == len(codes)  # codes are unique


def test_real_reference_data_has_provenance_not_placeholder_markers():
    data = json.loads(REFERENCE_PATH.read_text())
    assert "_warning" not in data  # stale "this is fake data" marker must not linger
    assert data["_meta"]["source_document"]
    assert data["_meta"]["entry_count"] == len(data["codes"])


def test_real_reference_data_retrieval_smoke_test():
    table = RamqReferenceTable.load(REFERENCE_PATH)
    results = table.candidates_for(
        "Patient avec douleur thoracique et suspicion d'infarctus, transfert pour angioplastie"
    )
    assert results  # real French clinical text should surface at least one candidate


def test_real_embedded_chunks_parse():
    chunks = _load_embedded_chunks(EMBEDDINGS_PATH)
    assert len(chunks) > 100
    for chunk in chunks:
        assert chunk.code
        assert len(chunk.embedding) == 1024

    models = {chunk.embedding_model for chunk in chunks}
    assert len(models) == 1  # a single ingestion run should use one embedding model throughout


def test_real_embedded_chunks_cover_most_reference_codes():
    data = json.loads(REFERENCE_PATH.read_text())
    reference_codes = {entry["code"] for entry in data["codes"]}
    chunks = _load_embedded_chunks(EMBEDDINGS_PATH)
    embedded_codes = {chunk.code for chunk in chunks}

    # The two files are generated independently by ramq-ingestion and can drift by a handful
    # of codes — a soft floor, not exact equality, catches a real regression (e.g. the wrong
    # file shipped, or an ingestion run that silently dropped most rows) without being brittle
    # to the exact drift count.
    covered = reference_codes & embedded_codes
    assert len(covered) / len(reference_codes) > 0.9
