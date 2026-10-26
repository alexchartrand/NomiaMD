"""The admin console's system, failures, lockouts, contact-request and audit endpoints."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.audit import AuditAction
from app.auth import get_current_user
from app.encounters.factory import get_extraction_queue
from app.intake import content_hash
from app.main import app
from app.postgresdb import (
    AuditEventFilter,
    AuditEventRepository,
    ContactRequestInput,
    ContactRequestRepository,
    ContactRole,
    ContactTopic,
    EncounterInput,
    EncounterRepository,
    Gender,
    LoginThrottle,
    LoginThrottleRepository,
    PatientRepository,
    UserRepository,
    UserRole,
    session_scope,
)

NOTE = "Note confidentielle du patient, ne jamais exposer."


@pytest.fixture
async def as_admin():
    async with session_scope() as session:
        admin = await UserRepository(session).create(
            email=f"sys-{uuid.uuid4().hex[:8]}@example.test", hashed_password="!", full_name="Admin Sys", role=UserRole.ADMIN
        )
    app.dependency_overrides[get_current_user] = lambda: admin
    yield admin


class _RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list[int] = []

    async def enqueue(self, encounter_id: int) -> None:
        self.enqueued.append(encounter_id)


@pytest.fixture
def queue():
    recording = _RecordingQueue()
    app.dependency_overrides[get_extraction_queue] = lambda: recording
    yield recording
    app.dependency_overrides.pop(get_extraction_queue, None)


async def _failed_encounter(*, with_patient: bool = True) -> int:
    async with session_scope() as session:
        patient_id = None
        if with_patient:
            patient = await PatientRepository(session).create(
                full_name="Patient Échec",
                ramq_number=f"FAIL{uuid.uuid4().int % 10**8:08d}",
                date_of_birth=date(1970, 1, 1),
                gender=Gender.MALE,
                is_vulnerable=False,
            )
            patient_id = patient.id
        encounters = EncounterRepository(session)
        encounter = await encounters.create(
            EncounterInput(
                user_id=1,
                patient_id=patient_id,
                source_system="manual",
                channel="paste",
                content_hash=content_hash(NOTE + uuid.uuid4().hex),
                note_text=NOTE,
            )
        )
        await encounters.record_extraction_error(encounter, "RuntimeError: model down")
        return encounter.id


def test_system_routes_are_admin_only():
    with TestClient(app) as client:
        for path in ("/admin/system", "/admin/extraction-failures", "/admin/lockouts", "/admin/contact-requests", "/admin/audit"):
            assert client.get(path).status_code == 403, path


async def test_system_report(as_admin):
    await _failed_encounter()
    with TestClient(app) as client:
        response = client.get("/admin/system")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] == {"ok": True, "detail": "sqlite"}
    assert body["codes_table"] == {"ok": True, "detail": "test-rev"}
    assert body["models"]["step_models"]["billing_codes"] == "mistral-medium-latest"
    assert body["row_counts"]["users"] >= 2
    assert body["failed_extractions"] >= 1


async def test_failed_extractions_list_metadata_never_the_note(as_admin):
    encounter_id = await _failed_encounter()
    with TestClient(app) as client:
        response = client.get("/admin/extraction-failures")

    assert response.status_code == 200
    [row] = [r for r in response.json() if r["encounter_id"] == encounter_id]
    assert row["error"] == "RuntimeError: model down"
    assert row["physician_name"] == "Dr. Test"
    assert NOTE not in response.text


async def test_retry_queues_the_encounter_and_is_audited(as_admin, queue):
    encounter_id = await _failed_encounter()
    with TestClient(app) as client:
        response = client.post(f"/admin/encounters/{encounter_id}/retry")

    assert response.status_code == 202
    assert queue.enqueued == [encounter_id]
    async with session_scope() as session:
        [event] = await AuditEventRepository(session).list(
            AuditEventFilter(user_id=as_admin.id, action=AuditAction.EXTRACTION_RETRIED.value)
        )
    assert event.details == {"encounter_id": encounter_id}


async def test_retry_refuses_an_encounter_without_patient(as_admin, queue):
    encounter_id = await _failed_encounter(with_patient=False)
    with TestClient(app) as client:
        response = client.post(f"/admin/encounters/{encounter_id}/retry")

    assert response.status_code == 404
    assert queue.enqueued == []


async def test_lockouts_list_and_unlock(as_admin):
    email = f"locked-{uuid.uuid4().hex[:8]}@example.test"
    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        await LoginThrottleRepository(session).add(
            LoginThrottle(email=email, failed_attempts=6, last_attempt_at=now, locked_until=now + timedelta(minutes=5))
        )

    with TestClient(app) as client:
        listed = client.get("/admin/lockouts").json()
        unlocked = client.delete(f"/admin/lockouts/{email.upper()}")
        after = client.get("/admin/lockouts").json()

    [row] = [r for r in listed if r["email"] == email]
    assert row["is_locked"] is True
    assert row["known_account"] is False
    assert unlocked.status_code == 204
    assert email not in [r["email"] for r in after]
    async with session_scope() as session:
        [event] = await AuditEventRepository(session).list(
            AuditEventFilter(user_id=as_admin.id, action=AuditAction.LOGIN_UNLOCKED.value)
        )
    assert event.details == {"email": email}


async def test_contact_requests_newest_first(as_admin):
    async with session_scope() as session:
        repo = ContactRequestRepository(session)
        for name in ("Premier", "Second"):
            await repo.create(
                ContactRequestInput(name=name, email="c@example.test", role=ContactRole.PHYSICIAN, topic=ContactTopic.DEMO)
            )

    with TestClient(app) as client:
        response = client.get("/admin/contact-requests", params={"limit": 2})

    assert [r["name"] for r in response.json()] == ["Second", "Premier"]


async def test_audit_list_names_actor_and_target(as_admin):
    with TestClient(app) as client:
        created = client.post(
            "/admin/users", json={"email": f"aud-{uuid.uuid4().hex[:8]}@example.test", "full_name": "Dr. Cible"}
        ).json()["user"]
        response = client.get("/admin/audit", params={"user_id": created["id"]})

    [event] = response.json()
    assert event["action"] == "user.created"
    assert event["actor_name"] == "Admin Sys"
    assert event["target_name"] == "Dr. Cible"
