"""Exercises the real reference_data.json fixture at the repo root of app/ramq/ — no
mocking needed, this is pure file parsing. Mirrors test_sample_patients.py's pattern for
"parses the real committed fixture" regression coverage.

Does NOT use the small_reference_table fixture from conftest.py (that's for tests that
should stay decoupled from the real data's size/content) — this test's whole point is to
check the real, promoted file."""

import json

from app.ramq.reference import REFERENCE_PATH, RamqReferenceTable


def test_real_reference_data_parses():
    table = RamqReferenceTable.load(REFERENCE_PATH)
    codes = table.all_codes()
    assert len(codes) > 500  # real manual has ~4,000 codes; a generous, stable-ish floor
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
