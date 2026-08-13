import json
from pathlib import Path

import pytest
from dotenv import load_dotenv
from llama_index.core.schema import NodeWithScore, TextNode

# app.tasks.registry builds a real, DB_PATH/MISTRAL_API_KEY-backed retriever the moment
# it's imported (BillingCodesTask's retriever is now constructed once at registry-import
# time, not looked up fresh per call) — and conftest.py is pytest's first import, before any
# test module gets a chance to load .env itself. Mirrors app/main.py's own load_dotenv call,
# needed here for the same reason.
load_dotenv(Path(__file__).parent.parent / ".env")

from app.tasks.registry import get_task  # noqa: E402

SMALL_REFERENCE_PATH = Path(__file__).parent / "fixtures" / "reference_data_test.json"


class _KeywordStubRetriever:
    """Deterministic, dependency-free stand-in for the real llama_index-backed retriever
    used in tests: ranks fixture candidates by how many of their fixture "keywords" appear
    in the query text. Only ever used here — the real pipeline always goes through
    RAMQCodesRetriever (app/ramq/vector_retrieval.py). Mimics BaseRetriever's `.retrieve()`
    (list[NodeWithScore] out), since that's the interface BillingCodesTask._retriever
    is used through (app/tasks/billing_codes/task.py's build_prompt)."""

    def __init__(self, entries: list[tuple[dict, list[str]]]):
        self._entries = entries

    def retrieve(self, query: str) -> list[NodeWithScore]:
        query_lower = query.lower()
        scored = [
            (metadata, sum(1 for kw in keywords if kw.lower() in query_lower))
            for metadata, keywords in self._entries
        ]
        ranked = sorted((pair for pair in scored if pair[1] > 0), key=lambda pair: pair[1], reverse=True)
        return [
            NodeWithScore(node=TextNode(text=metadata.get("description", ""), metadata=metadata), score=float(score))
            for metadata, score in ranked
        ]


@pytest.fixture(autouse=True)
def small_reference_table(monkeypatch):
    """Points RAMQ candidate retrieval at a tiny, stable fixture rather than the real
    (large, network-backed) llama_index vector store — tests need candidate narrowing to
    behave predictably without a real vector index, MISTRAL_API_KEY, or network call.

    Patches the `_retriever` attribute on the singleton BillingCodesTask instance held by
    app.tasks.registry, not a module-level function: BillingCodesTask now takes its
    retriever once at construction time (app/tasks/registry.py wires in
    get_ramq_retriever() when the registry module is first imported), rather than calling a
    lookup function fresh on every build_prompt(), so there's no module-level symbol left to
    monkeypatch.
    """
    data = json.loads(SMALL_REFERENCE_PATH.read_text())
    entries = [
        (
            {
                "number": entry["code"],
                "description": entry["description"],
                "when_to_use": entry.get("when_to_use", []),
                "rules": entry.get("rules", []),
                "fees": entry.get("fees", []),
            },
            entry.get("keywords", []),
        )
        for entry in data["codes"]
    ]
    stub_retriever = _KeywordStubRetriever(entries)

    monkeypatch.setattr(get_task("billing_codes"), "_retriever", stub_retriever)
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
