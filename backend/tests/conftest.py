import json
from pathlib import Path

import pytest

from app.ramq import reference as reference_module

SMALL_REFERENCE_PATH = Path(__file__).parent / "fixtures" / "reference_data_test.json"


class _KeywordStubRetriever:
    """Deterministic, dependency-free stand-in for the real llama_index-backed retriever
    used in tests: ranks fixture codes by how many of their fixture "keywords" appear in
    the query text. Only ever used here — the real pipeline always goes through
    RamqVectorRetriever (app/ramq/vector_retrieval.py)."""

    def __init__(self, entries: list[tuple[str, list[str]]]):
        self._entries = entries

    def candidates_for(self, query: str, limit: int) -> list[str]:
        query_lower = query.lower()
        scored = [
            (code, sum(1 for kw in keywords if kw.lower() in query_lower))
            for code, keywords in self._entries
        ]
        ranked = sorted((pair for pair in scored if pair[1] > 0), key=lambda pair: pair[1], reverse=True)
        return [code for code, _ in ranked[:limit]]


@pytest.fixture(autouse=True)
def small_reference_table(monkeypatch):
    """Points the RAMQ reference table at a tiny, stable fixture rather than the real
    (large, frequently-regenerated) reference_data.json, and swaps the real llama_index
    retriever for a deterministic keyword-based stub — tests need candidate narrowing to
    behave predictably without a real vector index, MISTRAL_API_KEY, or network call.

    Patches REFERENCE_PATH and get_vector_retriever (not get_reference_table itself): every
    caller of get_reference_table() imported that exact function object directly (e.g.
    `from app.ramq.reference import get_reference_table` in billing_codes.py) before this
    fixture ever runs, so replacing the reference.py module attribute wouldn't reach those
    callers — but the function body itself resolves REFERENCE_PATH/get_vector_retriever via
    reference.py's own module globals at call time, which patching here does reach.
    """
    data = json.loads(SMALL_REFERENCE_PATH.read_text())
    entries = [(entry["code"], entry.get("keywords", [])) for entry in data["codes"]]
    stub_retriever = _KeywordStubRetriever(entries)

    monkeypatch.setattr(reference_module, "REFERENCE_PATH", SMALL_REFERENCE_PATH)
    monkeypatch.setattr(reference_module, "get_vector_retriever", lambda: stub_retriever)
    reference_module.get_reference_table.cache_clear()
    yield
    reference_module.get_reference_table.cache_clear()


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch):
    """app/main.py loads .env at import time, so real API keys configured there (for
    actually running the app) would otherwise leak into every test process — silently
    enabling real network calls in tests that never asked for them. MISTRAL_API_KEY in
    particular now gates all RAMQ candidate retrieval (app/ramq/vector_retrieval.py), so a
    stray real key here would make small_reference_table's stub retriever pointless if any
    test path bypassed it."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
