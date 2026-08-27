import os
import shutil
import tempfile

# Route every test at a throwaway SQLite file instead of the developer's own dev DB.
# Must sit above the `from app...` imports below: app.postgresdb.database binds DATABASE_URL
# to a SQLAlchemy engine at import time, and app.config's load_dotenv(override=False) means
# a pre-set env var wins over anything in .env — so this has to run before any app import.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="nomiamd-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_DIR}/test.db"

import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.auth import get_current_user  # noqa: E402
from app.postgresdb import User, UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.ramq_codes import BillingCodesTask  # noqa: E402
from app.ramq_codes.models import Code, CodeFee  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.summary import ConsultationSummaryTask  # noqa: E402
from app.tasks.registry import register_tasks  # noqa: E402

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
def small_reference_table():
    """Points RAMQ candidate retrieval and code lookup at a tiny, stable fixture rather than
    the real (large, network-backed) llama_index vector store and LanceDB `codes` table —
    tests need candidate narrowing to behave predictably without a real vector index,
    MISTRAL_API_KEY, or network call.

    Populates app.tasks.registry's task dict directly with a BillingCodesTask built from
    these stubs (register_tasks — the same call app/bootstrap.py's init_tasks makes with
    real collaborators), rather than patching attributes on a pre-built singleton: nothing
    builds the task registry at import time any more (see app/bootstrap.py), so there's no
    singleton for this fixture to reach into until it makes one itself.
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

    register_tasks([
        BillingCodesTask(stub_retriever, stub_codes_data),
        ConsultationSummaryTask(),
    ])
    yield


@pytest.fixture(autouse=True)
def no_real_lancedb_on_startup(monkeypatch):
    """TestClient(app) as a context manager triggers app.main's lifespan, which normally
    opens a real LanceDB connection and rebuilds the task registry / chatbot engine from it
    (app/bootstrap.py's application_services()) — tests must not touch a real LanceDB, and
    must not clobber the stub registry small_reference_table just set up. Stubs out the
    lifespan's call to application_services with a no-op so init_db() (Postgres/SQLite) is
    the only real startup work TestClient still triggers.
    """

    @asynccontextmanager
    async def _fake_application_services():
        yield None

    monkeypatch.setattr("app.main.application_services", _fake_application_services)
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


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """slowapi's in-process storage (used whenever REDIS_URL is unset, as in tests) is a
    process-wide singleton keyed by client address — without a reset, login-heavy tests in
    test_auth.py would accumulate hits against each other and trip /auth/login's and
    /auth/me/password's 10/minute caps well before either test file's own request count
    would otherwise warrant it."""
    limiter.reset()
    yield


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def default_authenticated_user():
    """Overrides the get_current_user FastAPI dependency with a fixed, in-memory user (no
    DB row) for every test by default — route tests (test_extraction.py,
    test_ramq_chatbot_endpoint.py, test_sample_patients.py) exercise extraction/retrieval/
    patient logic, not auth, so they shouldn't need to know a login guard exists.

    tests/test_auth.py, which specifically tests that guard, pops this override at the top
    of the individual test bodies that need the real dependency; it comes back for every
    other test since this fixture re-runs per test.

    Pre-existing wart: this injects an in-memory User(id=1) with no DB row, so every test
    row's physician_id=1 is a dangling FK — harmless only because SQLite doesn't enforce
    foreign keys (see database.py)."""
    fake_user = User(
        id=1,
        email="physician@example.test",
        full_name="Dr. Test",
        role=UserRole.PHYSICIAN,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield fake_user
    app.dependency_overrides.pop(get_current_user, None)
