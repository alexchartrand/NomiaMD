import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from app.auth import get_current_user
from app.bootstrap import postgres_database
from app.postgresdb import PostgresDB, User, UserRole
from app.main import app
from app.lancedb.models import CodeRow, CodeRowFee
from app.lancedb.repository import ICodeRepository
from app.ramq_codes import BillingCodesTask, BillingContext
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.models import Code, CodeFee
from app.rate_limit import limiter
from app.summary import ConsultationSummaryResult, render_for_billing_codes
from app.summary import ConsultationSummaryTask
from app.tasks.registry import register_tasks
from tests.db_helpers import ensure_user_row

SMALL_REFERENCE_PATH = Path(__file__).parent / "fixtures" / "reference_data_test.json"


class _KeywordStubRetriever:
    """Deterministic, dependency-free stand-in for the real LanceDB-hybrid-search-backed
    retriever used in tests: ranks fixture candidates by how many of their fixture
    "keywords" appear in the rendered summary text. Only ever used here — the real
    pipeline always goes through RAMQCodesRetriever (app/ramq_codes/retriever.py). Mimics
    ICodesRetriever's `.aretrieve()` (a hybrid_search hit already carries the full row, not
    just a number, so there's no separate join step to stub), but skips eligibility
    filtering — the WHERE builder and UnresolvedAxisDetector have their own dedicated unit
    tests (test_lancedb_eligibility.py, test_ramq_codes_eligibility.py); this fixture's
    tiny made-up codes carry no eligibility bounds anyway."""

    def __init__(self, entries: list[tuple[Code, list[str]]]):
        self._entries = entries

    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        query_lower = render_for_billing_codes(summary).lower()
        scored = [
            (code, sum(1 for kw in keywords if kw.lower() in query_lower))
            for code, keywords in self._entries
        ]
        ranked = sorted((pair for pair in scored if pair[1] > 0), key=lambda pair: pair[1], reverse=True)
        return CandidateSet(candidates=[code for code, _score in ranked], unresolved_axes=())


class _StubCodeRepository(ICodeRepository):
    """Deterministic by-key lookup over the same fixture rows _KeywordStubRetriever ranks —
    stands in for the real LanceDB-backed CodeRepository so BillingCodesTask.resolve_fees can
    be exercised (see app/extraction/pipeline.py's post-extraction fee resolution) without a
    real LanceDB connection."""

    def __init__(self, rows: list[CodeRow]):
        self._rows_by_number = {row.number: row for row in rows}

    async def get_by_number(self, number: str) -> CodeRow:
        return self._rows_by_number[number]

    async def list_by_numbers(self, numbers: list[str]) -> list[CodeRow]:
        return [self._rows_by_number[n] for n in numbers if n in self._rows_by_number]

    async def hybrid_search(self, text: str, vector: list[float], k: int, eligibility=None) -> list:
        raise NotImplementedError("not exercised by BillingCodesTask.resolve_fees")


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
    entries = [
        (
            Code(
                number=entry["code"],
                description=entry["description"],
                when_to_use=tuple(entry.get("when_to_use", [])),
                rules=tuple(entry.get("rules", [])),
                fees=tuple(
                    CodeFee(
                        amount=f.get("amount"),
                        amount_text=f.get("amount_text"),
                        context=f.get("context"),
                        majoration=f.get("majoration"),
                        lieux=tuple(f.get("lieux", [])),
                    )
                    for f in entry.get("fees", [])
                ),
            ),
            entry.get("keywords", []),
        )
        for entry in data["codes"]
    ]
    stub_retriever = _KeywordStubRetriever(entries)

    rows = [
        CodeRow(
            number=entry["code"],
            description=entry["description"],
            header_path=entry.get("header_path", ""),
            when_to_use=entry.get("when_to_use", []),
            rules=entry.get("rules", []),
            fees=[CodeRowFee(**f) for f in entry.get("fees", [])],
        )
        for entry in data["codes"]
    ]
    stub_codes = _StubCodeRepository(rows)

    register_tasks([
        BillingCodesTask(stub_retriever, stub_codes),
        ConsultationSummaryTask(),
    ])
    yield


@pytest.fixture(autouse=True)
def no_real_lancedb_on_startup(monkeypatch):
    """TestClient(app) as a context manager triggers app.main's lifespan, which normally
    opens a real LanceDB connection and rebuilds the task registry / chatbot engine from it
    (app/bootstrap.py's application_services()) — tests must not touch a real LanceDB, and
    must not clobber the stub registry small_reference_table just set up. Stubs out the
    lifespan's call to application_services with a no-op, so TestClient triggers no real
    startup work — postgres_db already opened and bound the (SQLite) relational DB.
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
    # Same for the chat/embedding provider selection (app/llm/): a developer's .env pointing
    # at a real openai_compatible host must not leak into tests either.
    for name in (
        "LLM_PROVIDER", "LLM_ENDPOINT", "LLM_API_KEY",
        "EMBEDDING_PROVIDER", "EMBEDDING_ENDPOINT", "EMBEDDING_MODEL", "EMBEDDING_API_KEY",
        # And the Epic sandbox demo: a developer's flag/credentials must not turn its routes
        # on, or let a test reach fhir.epic.com (the contract test opts back in itself).
        "APP_ENV", "EPIC_SANDBOX_ENABLED", "EPIC_SANDBOX_CLIENT_ID", "EPIC_SANDBOX_PRIVATE_KEY_PATH",
        "EPIC_SANDBOX_KEY_ID",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """slowapi's in-process storage (used whenever REDIS_URL is unset, as in tests) is a
    process-wide singleton keyed by client address — without a reset, login-heavy tests in
    test_auth.py would accumulate hits against each other and trip /auth/login's and
    /auth/me/password's 10/minute caps well before either test file's own request count
    would otherwise warrant it."""
    limiter.reset()
    yield


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def postgres_db():
    """Routes every test at a throwaway SQLite file instead of the developer's own dev DB,
    opened once for the whole session and bound the way app/bootstrap.py binds the real one
    — so session_scope() (and every route's DbSession) works in any test without the app's
    lifespan, which no_real_lancedb_on_startup stubs out."""
    db_dir = tempfile.mkdtemp(prefix="nomiamd-test-")
    try:
        async with postgres_database(f"sqlite+aiosqlite:///{db_dir}/test.db") as db:
            yield db
    finally:
        shutil.rmtree(db_dir, ignore_errors=True)


@pytest.fixture
async def db_session(postgres_db: PostgresDB):
    """One session for a repository-level test, never committed: closing it at teardown
    rolls back everything the test wrote, so repository tests don't leak rows into each
    other. Tests that go through the API instead seed with session_scope (committed), since
    the app reads in its own sessions. SQLite holds its write lock until this session ends,
    so nothing else may write to the DB during a test using it — ensure_user_row in a
    fixture or before the first write is fine."""
    async with postgres_db.sessionmaker() as session:
        yield session


@pytest.fixture(autouse=True)
async def default_authenticated_user():
    """Overrides the get_current_user FastAPI dependency with a fixed, in-memory user (no
    DB row) for every test by default — route tests (test_extraction.py,
    test_ramq_chatbot_endpoint.py, test_sample_patients.py) exercise extraction/retrieval/
    patient logic, not auth, so they shouldn't need to know a login guard exists.

    tests/test_auth.py, which specifically tests that guard, pops this override at the top
    of the individual test bodies that need the real dependency; it comes back for every
    other test since this fixture re-runs per test.

    The injected User(id=1) is also seeded as a real `users` row (tests/db_helpers.py):
    SQLite enforces foreign keys now (see app/postgresdb/database.py), so every claim,
    extraction record or roster entry written under physician_id=1 needs it to exist."""
    fake_user = User(
        id=1,
        email="physician@example.test",
        full_name="Dr. Test",
        role=UserRole.PHYSICIAN,
        is_active=True,
    )
    await ensure_user_row(fake_user)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield fake_user
    app.dependency_overrides.pop(get_current_user, None)
