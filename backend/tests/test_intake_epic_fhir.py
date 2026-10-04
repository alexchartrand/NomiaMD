"""The Epic sandbox connector (step 11b): the pure mapper on fixture resources, the client,
token provider and reader over an httpx.MockTransport serving tests/fixtures/epic/ (never
the network), the connector through IntakeService against the test DB, and the flag-gated
routes. The live sandbox has its own opt-in contract test (test_epic_sandbox_contract.py)."""

import base64
import itertools
import json
from datetime import date, time
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.config import settings
from app.extraction.encounter_date import DateOrder
from app.intake import Channel, DedupOutcome, IntakeService, default_normalizers
from app.intake.connectors.epic_fhir import (
    EPIC_SANDBOX_SOURCE_SYSTEM,
    BackendServicesTokenProvider,
    EpicFhirClient,
    EpicFhirError,
    EpicNoteMapper,
    EpicNoteReader,
    EpicSandboxConnector,
    EpicSandboxInProductionError,
    SandboxIdentifierStrategy,
    SandboxPatient,
    SandboxRoster,
    demo_nam,
)
from app.intake.connectors.epic_fhir.factory import check_sandbox_startup
from app.intake.dependencies import get_epic_sandbox_connector, get_epic_sandbox_roster
from app.intake.normalizers import HtmlNormalizer
from app.main import app
from app.patients import nam as nam_module
from app.postgresdb import Gender, PatientRepository, session_scope
from tests.db_helpers import ensure_user_row, physician
from tests.test_intake_service import RecordingQueue

FIXTURES = Path(__file__).parent / "fixtures" / "epic"
BASE_URL = "https://fhir.example.test/api/FHIR/R4/"
TOKEN_URL = "https://fhir.example.test/oauth2/token"
CAMILA_ID = "erXuFYUfucBZaryVksYEcMg3"

_physician_ids = itertools.count(6100)
# Each test's roster gets its own fake NAM, so the shared test DB never holds two patients
# for one: "EPIC" + a counter, well-formed but not a real birth date (only resolution reads it).
_fake_nams = itertools.count(1)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


NOTE_HTML = (FIXTURES / "note.html").read_text(encoding="utf-8")


class FakeEpic:
    """The sandbox's answers, by path. Records what was asked so tests can check headers."""

    def __init__(self, patient: dict | None = None, documents: dict | None = None) -> None:
        self.routes: dict[str, httpx.Response] = {
            "/oauth2/token": httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600}),
            f"/api/FHIR/R4/Patient/{CAMILA_ID}": httpx.Response(200, json=patient or _fixture("patient.json")),
            "/api/FHIR/R4/DocumentReference": httpx.Response(
                200, json=documents or _fixture("document_references.json")
            ),
            "/api/FHIR/R4/Encounter/eOfficeVisit3": httpx.Response(200, json=_fixture("encounter.json")),
            "/api/FHIR/R4/Binary/fSignedProgressNoteHtml3": httpx.Response(
                200, text=NOTE_HTML, headers={"content-type": "text/html"}
            ),
        }
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.routes.get(request.url.path)
        return response if response is not None else httpx.Response(404, json={"resourceType": "OperationOutcome"})

    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


class StaticTokens:
    async def token(self) -> str:
        return "static-token"


def _roster(nam: str = "LOPC87591299", note_ids: frozenset[str] = frozenset({"eSignedProgressNote3"})) -> SandboxRoster:
    return SandboxRoster(
        [SandboxPatient(CAMILA_ID, "Lopez", "Camila", date(1987, 9, 12), Gender.FEMALE, nam, note_ids)]
    )


def _mapper(roster: SandboxRoster | None = None) -> EpicNoteMapper:
    return EpicNoteMapper(SandboxIdentifierStrategy(roster or _roster()), EPIC_SANDBOX_SOURCE_SYSTEM)


def _reader(fake: FakeEpic, http: httpx.AsyncClient, roster: SandboxRoster | None = None) -> EpicNoteReader:
    return EpicNoteReader(EpicFhirClient(http, BASE_URL, StaticTokens()), _mapper(roster))


def _documents() -> list[dict]:
    return [entry["resource"] for entry in _fixture("document_references.json")["entry"]]


@pytest.fixture(scope="module")
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


# --- EpicNoteMapper ---------------------------------------------------------------------


def test_mapper_keeps_signed_notes_and_drops_drafts_and_errors():
    signed, draft, error, _outcome = _documents()

    assert EpicNoteMapper.is_signed(signed)
    assert not EpicNoteMapper.is_signed(draft)
    assert not EpicNoteMapper.is_signed(error)


def test_mapper_reads_the_html_attachment_not_the_rtf_one():
    signed = _documents()[0]

    assert EpicNoteMapper.note_attachment(signed)["url"] == "Binary/fSignedProgressNoteHtml3"


def test_mapper_builds_the_source_note_from_structured_fields():
    signed = _documents()[0]

    note = _mapper().to_source_note(signed, NOTE_HTML, _fixture("patient.json"), _fixture("encounter.json"))

    assert note.source_system == EPIC_SANDBOX_SOURCE_SYSTEM
    assert note.channel == Channel.FHIR_PULL
    assert note.external_note_id == "eSignedProgressNote3"
    assert note.external_encounter_id == "eOfficeVisit3"
    # The identifier strategy, not the patient's US identifiers.
    assert note.nam == "LOPC87591299"
    # 19:30Z is 15:30 in Montréal (EDT): times are the clinic's wall clock.
    assert note.service_date == date(2023, 6, 2)
    assert note.meta.time_start == time(15, 30)
    assert note.meta.time_end == time(16, 0)
    assert note.meta.location_label == "EMC Family Medicine"
    assert note.meta.author_ref == "Practitioner/eFamilyMedicineMD3"
    assert note.meta.source_version == "2"
    assert note.text == NOTE_HTML


def test_mapper_dates_an_evening_visit_on_the_clinic_day_not_the_utc_one():
    encounter = _fixture("encounter.json") | {"period": {"start": "2023-06-03T01:30:00Z"}}

    assert _mapper().service_date(_documents()[0], encounter) == date(2023, 6, 2)


def test_mapper_invents_no_times_for_a_date_only_period():
    signed = _documents()[0]
    encounter = _fixture("encounter.json") | {"period": {"start": "2023-06-02"}}

    note = _mapper().to_source_note(signed, NOTE_HTML, _fixture("patient.json"), encounter)

    assert note.service_date == date(2023, 6, 2)
    assert note.meta.time_start is None
    assert note.meta.time_end is None


def test_mapper_falls_back_to_the_note_period_without_an_encounter():
    note = _mapper().to_source_note(_documents()[0], NOTE_HTML, _fixture("patient.json"), None)

    assert note.service_date == date(2023, 6, 2)
    assert note.external_encounter_id is None
    assert note.meta.time_start is None


def test_mapper_leaves_a_patient_off_the_roster_unresolved():
    patient = _fixture("patient.json") | {"id": "eSomeoneElse"}

    note = _mapper().to_source_note(_documents()[0], NOTE_HTML, patient, None)

    assert note.nam is None


def test_epic_sandbox_notes_are_html_with_month_first_dates():
    normalizer = default_normalizers().for_source(EPIC_SANDBOX_SOURCE_SYSTEM)

    assert isinstance(normalizer, HtmlNormalizer)
    assert normalizer.date_order == DateOrder.MDY
    text = normalizer.normalize(NOTE_HTML)
    assert "p { margin" not in text
    assert "Assessment & Plan:" in text
    assert "seen on 06/02/2023" in text


# --- the mapper on responses recorded from the live sandbox ------------------------------

RECORDED = FIXTURES / "recorded" / "e63wRTbPfr1p8UW81d8Seiw3"  # Theodore Mychart


def _recorded(name: str):
    return json.loads((RECORDED / name).read_text(encoding="utf-8"))


def test_recorded_sandbox_notes_keep_signed_and_drop_drafts():
    documents = _recorded("DocumentReference.json")

    signed = [doc["id"] for doc in documents if EpicNoteMapper.is_signed(doc)]
    drafts = [doc["id"] for doc in documents if doc.get("docStatus") == "preliminary"]

    assert "e-OoWva4weY3KsNaVR45Y3A3" in signed
    assert drafts and not set(drafts) & set(signed)


def test_recorded_sandbox_note_maps_with_the_date_but_no_invented_time():
    document = next(doc for doc in _recorded("DocumentReference.json") if doc["id"] == "e-OoWva4weY3KsNaVR45Y3A3")
    encounter = _recorded(f"{EpicNoteMapper.encounter_reference(document).replace('/', '-')}.json")
    roster = SandboxRoster(
        [SandboxPatient("e63wRTbPfr1p8UW81d8Seiw3", "Mychart", "Theodore", date(1948, 7, 7), Gender.MALE, "MYCT48070799")]
    )
    html = (RECORDED / "Binary-e-OoWva4weY3KsNaVR45Y3A3.html").read_text(encoding="utf-8")

    note = _mapper(roster).to_source_note(document, html, _recorded("Patient.json"), encounter)

    assert note.nam == "MYCT48070799"
    assert note.service_date == date(2007, 7, 25)
    # Epic's sandbox writes "no time" as a zero-length period at Central midnight (05:00Z).
    assert encounter["period"]["start"] == encounter["period"]["end"]
    assert note.meta.time_start is None
    assert note.meta.time_end is None
    assert note.meta.location_label == "EMC Family Medicine"
    text = default_normalizers().for_source(EPIC_SANDBOX_SOURCE_SYSTEM).normalize(note.text)
    assert text.startswith("SUBJECTIVE:")


# --- demo NAMs --------------------------------------------------------------------------


def test_demo_nam_decodes_back_to_the_sandbox_patient():
    built = demo_nam("Lopez", "Camila", date(1987, 9, 12), Gender.FEMALE)

    assert built == "LOPC87591299"
    decoded = nam_module.decode(built, on_date=date(2026, 10, 3))
    assert decoded.date_of_birth == date(1987, 9, 12)
    assert decoded.gender == Gender.FEMALE


def test_demo_nam_strips_accents_and_pads_short_names():
    assert demo_nam("Lé", "Élie", date(1973, 6, 3), Gender.MALE) == "LEXE73060399"


def test_roster_without_a_file_is_empty(tmp_path):
    assert len(SandboxRoster.load(tmp_path / "missing.json")) == 0


# --- EpicFhirClient ---------------------------------------------------------------------


async def test_client_follows_next_links_and_skips_outcome_entries():
    first = {
        "resourceType": "Bundle",
        "link": [{"relation": "next", "url": f"{BASE_URL}DocumentReference?page=2"}],
        "entry": [{"resource": {"resourceType": "DocumentReference", "id": "a"}, "search": {"mode": "match"}}],
    }
    second = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "DocumentReference", "id": "b"}, "search": {"mode": "match"}},
            {"resource": {"resourceType": "OperationOutcome"}, "search": {"mode": "outcome"}},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=second if request.url.params.get("page") == "2" else first)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        found = await EpicFhirClient(http, BASE_URL, StaticTokens()).search("DocumentReference", {"patient": "x"})

    assert [resource["id"] for resource in found] == ["a", "b"]


async def test_client_sends_the_bearer_token_and_raises_on_errors():
    fake = FakeEpic()
    async with fake.http() as http:
        client = EpicFhirClient(http, BASE_URL, StaticTokens())
        await client.read("Patient", CAMILA_ID)
        with pytest.raises(EpicFhirError) as raised:
            await client.read("Patient", "eUnknown")

    assert fake.requests[0].headers["Authorization"] == "Bearer static-token"
    assert raised.value.status_code == 404


async def test_client_decodes_a_binary_returned_as_fhir_json():
    payload = {"resourceType": "Binary", "contentType": "text/html", "data": base64.b64encode(b"<p>Note</p>").decode()}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, headers={"content-type": "application/fhir+json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        text = await EpicFhirClient(http, BASE_URL, StaticTokens()).binary_text("Binary/x", "text/html")

    assert text == "<p>Note</p>"


# --- BackendServicesTokenProvider -------------------------------------------------------


async def test_token_provider_signs_an_rs384_assertion_for_the_client_id(private_key_pem):
    fake = FakeEpic()
    async with fake.http() as http:
        token = await BackendServicesTokenProvider(
            http, TOKEN_URL, "client-123", private_key_pem, key_id="key-1", now=lambda: 1_000_000
        ).token()

    assert token == "token-1"
    form = dict(httpx.QueryParams(fake.requests[0].content.decode()))
    assert form["grant_type"] == "client_credentials"
    assert form["client_assertion_type"] == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    assertion = form["client_assertion"]
    assert jwt.get_unverified_header(assertion) == {"alg": "RS384", "typ": "JWT", "kid": "key-1"}
    public_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None).public_key()
    claims = jwt.decode(
        assertion, public_key, algorithms=["RS384"], audience=TOKEN_URL, options={"verify_exp": False}
    )
    assert claims["iss"] == claims["sub"] == "client-123"
    assert claims["exp"] - claims["iat"] <= 300


async def test_token_provider_reuses_its_token_until_close_to_expiry(private_key_pem):
    clock = [1_000_000.0]
    fake = FakeEpic()
    async with fake.http() as http:
        provider = BackendServicesTokenProvider(http, TOKEN_URL, "client-123", private_key_pem, now=lambda: clock[0])
        await provider.token()
        clock[0] += 3000
        await provider.token()
        clock[0] += 560  # within a minute of the hour's expiry
        await provider.token()

    assert len(fake.requests) == 2


async def test_token_provider_raises_when_epic_refuses_the_assertion(private_key_pem):
    fake = FakeEpic()
    fake.routes["/oauth2/token"] = httpx.Response(400, json={"error": "invalid_client"})
    async with fake.http() as http:
        with pytest.raises(EpicFhirError):
            await BackendServicesTokenProvider(http, TOKEN_URL, "client-123", private_key_pem).token()


# --- EpicNoteReader ---------------------------------------------------------------------


async def test_reader_returns_only_the_signed_note_with_its_html_body():
    fake = FakeEpic()
    async with fake.http() as http:
        notes = await _reader(fake, http).signed_notes(CAMILA_ID)

    [note] = notes
    assert note.external_note_id == "eSignedProgressNote3"
    assert note.text == NOTE_HTML
    assert note.meta.time_start == time(15, 30)
    search = next(r for r in fake.requests if r.url.path.endswith("/DocumentReference"))
    assert search.url.params["patient"] == CAMILA_ID
    assert search.url.params["category"] == "clinical-note"
    binary = next(r for r in fake.requests if "/Binary/" in r.url.path)
    assert binary.headers["Accept"] == "text/html"
    # The draft's body is never fetched.
    assert not any("fDraftHtml3" in r.url.path for r in fake.requests)


async def test_reader_fetches_no_body_for_a_note_include_leaves_out():
    fake = FakeEpic()
    async with fake.http() as http:
        notes = await _reader(fake, http).signed_notes(CAMILA_ID, include=lambda doc: False)

    assert notes == []
    assert not any("/Binary/" in r.url.path for r in fake.requests)


async def test_reader_skips_notes_before_since():
    fake = FakeEpic()
    async with fake.http() as http:
        notes = await _reader(fake, http).signed_notes(CAMILA_ID, since=date(2023, 6, 3))

    assert notes == []
    assert not any("/Binary/" in r.url.path for r in fake.requests)


async def test_reader_keeps_a_note_whose_encounter_is_unreadable():
    fake = FakeEpic()
    fake.routes["/api/FHIR/R4/Encounter/eOfficeVisit3"] = httpx.Response(403, json={"resourceType": "OperationOutcome"})
    async with fake.http() as http:
        [note] = await _reader(fake, http).signed_notes(CAMILA_ID)

    assert note.meta.time_start is None
    assert note.service_date == date(2023, 6, 2)


# --- EpicSandboxConnector through IntakeService -----------------------------------------


@pytest.fixture
async def user():
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    return user


async def _seed_demo_patient() -> SandboxRoster:
    fake_nam = f"EPIC{next(_fake_nams):08d}"
    async with session_scope() as session:
        await PatientRepository(session).create(
            full_name="Camila Lopez",
            ramq_number=fake_nam,
            date_of_birth=date(1987, 9, 12),
            gender=Gender.FEMALE,
            is_vulnerable=False,
        )
    return _roster(fake_nam)


async def test_connector_notes_resolve_through_the_fake_nam_and_reimport_is_a_duplicate(user):
    roster = await _seed_demo_patient()
    queue = RecordingQueue()
    service = IntakeService(queue)
    fake = FakeEpic()

    async with fake.http() as http:
        connector = EpicSandboxConnector(_reader(fake, http, roster), roster)
        first = await service.receive_all(await connector.fetch_signed_notes(user), user)
        again = await service.receive_all(await connector.fetch_signed_notes(user), user)

    [received] = first
    assert received.outcome == DedupOutcome.NEW
    assert received.patient_id is not None
    assert queue.enqueued == [received.encounter_id]
    assert [(o.outcome, o.encounter_id) for o in again] == [(DedupOutcome.DUPLICATE, received.encounter_id)]


async def test_connector_imports_only_the_roster_notes(user):
    fake = FakeEpic()
    roster = _roster(note_ids=frozenset({"eSomeOtherNote"}))

    async with fake.http() as http:
        notes = await EpicSandboxConnector(_reader(fake, http, roster), roster).fetch_signed_notes(user)

    # The signed note isn't listed: other apps' test notes in the shared sandbox look the same.
    assert notes == []
    assert not any("/Binary/" in r.url.path for r in fake.requests)


# --- Routes and the flag ----------------------------------------------------------------


class StubConnector:
    def __init__(self, notes=None, error: Exception | None = None) -> None:
        self._notes = notes or []
        self._error = error

    async def fetch_signed_notes(self, user, since=None):
        if self._error is not None:
            raise self._error
        return self._notes


@pytest.fixture
async def me():
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_epic_sandbox_connector, None)
    app.dependency_overrides.pop(get_epic_sandbox_roster, None)


def test_sandbox_routes_are_404_when_the_flag_is_off(me, client):
    assert client.get("/intake/epic-sandbox").status_code == 404
    assert client.post("/intake/epic-sandbox/import").status_code == 404


def test_sandbox_status_reports_the_roster_size(me, client, monkeypatch):
    monkeypatch.setenv("EPIC_SANDBOX_ENABLED", "true")
    app.dependency_overrides[get_epic_sandbox_roster] = lambda: _roster()

    response = client.get("/intake/epic-sandbox")

    assert response.status_code == 200
    assert response.json() == {"patients": 1}


async def test_sandbox_import_receives_the_notes_once(me, client, monkeypatch):
    monkeypatch.setenv("EPIC_SANDBOX_ENABLED", "true")
    roster = await _seed_demo_patient()
    note = _mapper(roster).to_source_note(
        _documents()[0], NOTE_HTML, _fixture("patient.json"), _fixture("encounter.json")
    )
    app.dependency_overrides[get_epic_sandbox_connector] = lambda: StubConnector([note])
    # Received notes are extracted inline; this test is about intake, not extraction.
    client.app.state.intake_service = IntakeService(RecordingQueue())

    first = client.post("/intake/epic-sandbox/import")
    again = client.post("/intake/epic-sandbox/import")

    assert first.status_code == 200
    [received] = first.json()
    assert received["outcome"] == "new"
    assert received["patient_id"] is not None
    assert [o["outcome"] for o in again.json()] == ["duplicate"]


def test_sandbox_import_with_no_notes_returns_an_empty_list(me, client, monkeypatch):
    monkeypatch.setenv("EPIC_SANDBOX_ENABLED", "true")
    app.dependency_overrides[get_epic_sandbox_connector] = lambda: StubConnector([])

    response = client.post("/intake/epic-sandbox/import")

    assert response.status_code == 200
    assert response.json() == []


def test_sandbox_import_reports_an_epic_failure_as_502(me, client, monkeypatch):
    monkeypatch.setenv("EPIC_SANDBOX_ENABLED", "true")
    app.dependency_overrides[get_epic_sandbox_connector] = lambda: StubConnector(
        error=EpicFhirError(401, TOKEN_URL, "invalid_client")
    )

    assert client.post("/intake/epic-sandbox/import").status_code == 502


def test_startup_refuses_the_sandbox_flag_in_production(monkeypatch):
    monkeypatch.setenv("EPIC_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(EpicSandboxInProductionError):
        check_sandbox_startup(settings)


def test_startup_requires_the_key_file_when_the_flag_is_on(monkeypatch, tmp_path):
    monkeypatch.setenv("EPIC_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("EPIC_SANDBOX_CLIENT_ID", "client-123")
    monkeypatch.setenv("EPIC_SANDBOX_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem"))

    with pytest.raises(FileNotFoundError):
        check_sandbox_startup(settings)


def test_startup_ignores_the_sandbox_settings_when_the_flag_is_off(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    check_sandbox_startup(settings)
