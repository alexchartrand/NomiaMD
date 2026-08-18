import json
from pathlib import Path

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

# app.tasks.registry builds a real, DB_PATH/MISTRAL_API_KEY-backed retriever the moment
# it's imported (BillingCodesTask's retriever is now constructed once at registry-import
# time, not looked up fresh per call). That chain imports app.config, which loads .env on
# its own first import — so .env is guaranteed to be loaded before any of these env-derived
# settings are read, regardless of which module happens to import app.config first.
from app.ramq_codes.models import Code, CodeFee  # noqa: E402
from app.tasks.registry import get_task  # noqa: E402

SMALL_REFERENCE_PATH = Path(__file__).parent / "fixtures" / "reference_data_test.json"


class _KeywordStubRetriever:
    """Deterministic, dependency-free stand-in for the real llama_index-backed retriever
    used in tests: ranks fixture candidates by how many of their fixture "keywords" appear
    in the query text. Only ever used here — the real pipeline always goes through
    RAMQCodesRetriever (app/ramq_codes/retriever.py). Mimics BaseRetriever's `.aretrieve()`
    (list[NodeWithScore] out), since that's the interface BillingCodesTask._retriever
    is used through (app/ramq_codes/task.py's build_prompt). Node metadata carries only
    `number`, mirroring the real `code-embeddings` table's node shape — BillingCodesTask
    joins full candidate data (description/when_to_use/rules/fees) in via `_codes_data`,
    not off retriever node metadata, so that's all the stub needs to provide."""

    def __init__(self, entries: list[tuple[str, list[str]]]):
        self._entries = entries

    def retrieve(self, query: str) -> list[NodeWithScore]:
        query_lower = query.lower()
        scored = [
            (number, sum(1 for kw in keywords if kw.lower() in query_lower))
            for number, keywords in self._entries
        ]
        ranked = sorted((pair for pair in scored if pair[1] > 0), key=lambda pair: pair[1], reverse=True)
        return [
            NodeWithScore(node=TextNode(text="", metadata={"number": number}), score=float(score))
            for number, score in ranked
        ]

    async def aretrieve(self, query: str) -> list[NodeWithScore]:
        return self.retrieve(query)


class _StubCodesData:
    """Deterministic, dependency-free stand-in for CodesData (app/ramq_codes/codes_data.py):
    looks candidate numbers up in a fixed in-memory table instead of joining against the
    real (large, network-embedding-backed) LanceDB `codes` table. Mimics CodesData's
    `.get()` (list[Code] out, silently dropping numbers with no matching row), since that's
    the interface BillingCodesTask._codes_data is used through."""

    def __init__(self, codes_by_number: dict[str, Code]):
        self._codes_by_number = codes_by_number

    async def get(self, numbers: list[str]) -> list[Code]:
        return [self._codes_by_number[n] for n in numbers if n in self._codes_by_number]


@pytest.fixture(autouse=True)
def small_reference_table(monkeypatch):
    """Points RAMQ candidate retrieval and code lookup at a tiny, stable fixture rather than
    the real (large, network-backed) llama_index vector store and LanceDB `codes` table —
    tests need candidate narrowing to behave predictably without a real vector index,
    MISTRAL_API_KEY, or network call.

    Patches the `_retriever` and `_codes_data` attributes on the singleton BillingCodesTask
    instance held by app.tasks.registry, not module-level functions: BillingCodesTask now
    takes both at construction time (app/tasks/registry.py wires in get_ramq_retriever() and
    get_codes_data() when the registry module is first imported), rather than calling a
    lookup function fresh on every build_prompt(), so there's no module-level symbol left to
    monkeypatch.
    """
    data = json.loads(SMALL_REFERENCE_PATH.read_text())
    entries = [(entry["code"], entry.get("keywords", [])) for entry in data["codes"]]
    stub_retriever = _KeywordStubRetriever(entries)

    codes_by_number = {
        entry["code"]: Code(
            number=entry["code"],
            description=entry["description"],
            confidence=1.0,
            when_to_use=tuple(entry.get("when_to_use", [])),
            rules=tuple(entry.get("rules", [])),
            fees=tuple(
                CodeFee(amount=f.get("amount"), when_to_use=f.get("when_to_use"), majoration=f.get("majoration"))
                for f in entry.get("fees", [])
            ),
        )
        for entry in data["codes"]
    }
    stub_codes_data = _StubCodesData(codes_by_number)

    task = get_task("billing_codes")
    monkeypatch.setattr(task, "_retriever", stub_retriever)
    monkeypatch.setattr(task, "_codes_data", stub_codes_data)
    yield


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch):
    """app/main.py loads .env at import time, so real API keys configured there (for
    actually running the app) would otherwise leak into every test process — silently
    enabling real network calls in tests that never asked for them. MISTRAL_API_KEY in
    particular now gates all RAMQ candidate retrieval (app/ramq_codes/retriever.py), so a
    stray real key here would make small_reference_table's stub retriever pointless if any
    test path bypassed it."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
