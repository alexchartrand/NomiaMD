import json
from pathlib import Path

import pytest

from app.ramq.vector_retrieval import RamqCandidate
from app.tasks import billing_codes as billing_codes_module

SMALL_REFERENCE_PATH = Path(__file__).parent / "fixtures" / "reference_data_test.json"


class _KeywordStubRetriever:
    """Deterministic, dependency-free stand-in for the real llama_index-backed retriever
    used in tests: ranks fixture candidates by how many of their fixture "keywords" appear
    in the query text. Only ever used here — the real pipeline always goes through
    RamqVectorRetriever (app/ramq/vector_retrieval.py)."""

    def __init__(self, entries: list[tuple[RamqCandidate, list[str]]]):
        self._entries = entries

    def candidates_for(self, query: str, limit: int) -> list[RamqCandidate]:
        query_lower = query.lower()
        scored = [
            (candidate, sum(1 for kw in keywords if kw.lower() in query_lower))
            for candidate, keywords in self._entries
        ]
        ranked = sorted((pair for pair in scored if pair[1] > 0), key=lambda pair: pair[1], reverse=True)
        return [candidate for candidate, _ in ranked[:limit]]


@pytest.fixture(autouse=True)
def small_reference_table(monkeypatch):
    """Points RAMQ candidate retrieval at a tiny, stable fixture rather than the real
    (large, network-backed) llama_index vector store — tests need candidate narrowing to
    behave predictably without a real vector index, MISTRAL_API_KEY, or network call.

    Patches billing_codes_module.get_vector_retriever, not
    app.ramq.vector_retrieval.get_vector_retriever itself: billing_codes.py imported that
    exact function object directly (`from app.ramq.vector_retrieval import
    get_vector_retriever`) at module load time, so replacing the vector_retrieval module
    attribute wouldn't reach that already-bound name.
    """
    data = json.loads(SMALL_REFERENCE_PATH.read_text())
    entries = [
        (
            RamqCandidate(
                code=entry["code"],
                description=entry["description"],
                when_to_use=tuple(entry.get("when_to_use", [])),
                rules=tuple(entry.get("rules", [])),
            ),
            entry.get("keywords", []),
        )
        for entry in data["codes"]
    ]
    stub_retriever = _KeywordStubRetriever(entries)

    monkeypatch.setattr(billing_codes_module, "get_vector_retriever", lambda: stub_retriever)
    yield


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
