"""The admin console's account management (/admin/users): admins only, temporary passwords
that force a change, deactivation instead of deletion, session revocation, and the guards
that keep the console from locking itself out."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.audit import AuditAction
from app.auth import get_authenticated_user, get_current_user
from app.main import app
from app.postgresdb import AuditEventFilter, AuditEventRepository, User, UserRepository, UserRole, session_scope
from tests.db_helpers import ensure_user_row

ADMIN = User(id=900, email="admin@example.test", full_name="Admin", role=UserRole.ADMIN, is_active=True)


@pytest.fixture
async def as_admin():
    await ensure_user_row(ADMIN)
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    yield ADMIN


def _email() -> str:
    return f"new-{uuid.uuid4().hex[:8]}@example.test"


def _create(client: TestClient, **overrides):
    body = {"email": _email(), "full_name": "Dr. Nouveau", "role": "physician", **overrides}
    return client.post("/admin/users", json=body)


async def _events(user_id: int) -> list[str]:
    async with session_scope() as session:
        return [e.action for e in await AuditEventRepository(session).list(AuditEventFilter(user_id=user_id))]


def test_physicians_are_refused():
    with TestClient(app) as client:
        assert client.get("/admin/users").status_code == 403
        assert _create(client).status_code == 403


async def test_create_returns_a_temporary_password_that_must_be_changed(as_admin):
    with TestClient(app) as client:
        response = _create(client, email="  Mixed.Case@Example.TEST ".replace("Mixed", uuid.uuid4().hex[:6]),
                           panel_size=900, remuneration_type="mixte")
        listed = client.get("/admin/users")

    assert response.status_code == 201
    body = response.json()
    assert len(body["temporary_password"]) >= 16
    user = body["user"]
    assert user["email"] == user["email"].strip().lower()
    assert user["must_change_password"] is True
    assert user["panel_size"] == 900
    assert user["id"] in [u["id"] for u in listed.json()]
    assert await _events(user["id"]) == [AuditAction.USER_CREATED.value]


async def test_temporary_password_logs_in_into_the_password_gate(as_admin):
    with TestClient(app) as client:
        created = _create(client).json()

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_authenticated_user, None)
    with TestClient(app) as client:
        login = client.post(
            "/auth/login", json={"email": created["user"]["email"], "password": created["temporary_password"]}
        )
        blocked = client.get("/patients")

    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert blocked.status_code == 403


async def test_duplicate_email_is_a_409(as_admin):
    email = _email()
    with TestClient(app) as client:
        _create(client, email=email)
        response = _create(client, email=email)

    assert response.status_code == 409


async def test_update_records_changed_field_names_only(as_admin):
    with TestClient(app) as client:
        user = _create(client).json()["user"]
        response = client.patch(
            f"/admin/users/{user['id']}",
            json={"full_name": "Dr. Renommé", "role": "physician", "panel_size": 1200},
        )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Dr. Renommé"
    async with session_scope() as session:
        [updated, _created] = await AuditEventRepository(session).list(AuditEventFilter(user_id=user["id"]))
    assert updated.details == {"fields": ["full_name", "panel_size"]}


async def test_deactivate_and_reactivate(as_admin):
    with TestClient(app) as client:
        user = _create(client).json()["user"]
        deactivated = client.post(f"/admin/users/{user['id']}/deactivate")
        reactivated = client.post(f"/admin/users/{user['id']}/reactivate")

    assert deactivated.json()["is_active"] is False
    assert deactivated.json()["deactivated_at"] is not None
    assert reactivated.json()["is_active"] is True
    assert reactivated.json()["deactivated_at"] is None
    assert await _events(user["id"]) == [
        AuditAction.USER_REACTIVATED.value,
        AuditAction.USER_DEACTIVATED.value,
        AuditAction.USER_CREATED.value,
    ]


async def test_reset_password_ends_open_sessions(as_admin):
    with TestClient(app) as admin_client:
        created = _create(admin_client).json()
    user_id = created["user"]["id"]

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_authenticated_user, None)
    with TestClient(app) as user_client:
        user_client.post(
            "/auth/login", json={"email": created["user"]["email"], "password": created["temporary_password"]}
        )
        assert user_client.get("/auth/me").status_code == 200

        app.dependency_overrides[get_current_user] = lambda: ADMIN
        with TestClient(app) as admin_client:
            reset = admin_client.post(f"/admin/users/{user_id}/reset-password")
        app.dependency_overrides.pop(get_current_user, None)

        assert user_client.get("/auth/me").status_code == 401

    assert reset.status_code == 200
    assert reset.json()["temporary_password"] != created["temporary_password"]


async def test_revoke_sessions_bumps_the_session_version(as_admin):
    with TestClient(app) as client:
        user = _create(client).json()["user"]
        response = client.post(f"/admin/users/{user['id']}/revoke-sessions")

    assert response.status_code == 204
    async with session_scope() as session:
        assert (await UserRepository(session).get_by_id(user["id"])).session_version == 1


async def test_admin_cannot_deactivate_or_demote_themselves(as_admin):
    with TestClient(app) as client:
        deactivate = client.post(f"/admin/users/{ADMIN.id}/deactivate")
        demote = client.patch(f"/admin/users/{ADMIN.id}", json={"full_name": "Admin", "role": "physician"})
        reset = client.post(f"/admin/users/{ADMIN.id}/reset-password")

    assert deactivate.status_code == 409
    assert demote.status_code == 409
    assert reset.status_code == 409


async def test_last_active_admin_cannot_be_deactivated(as_admin, monkeypatch):
    with TestClient(app) as client:
        other_admin = _create(client, role="admin").json()["user"]

    async def only_one(self) -> int:
        return 1

    monkeypatch.setattr(UserRepository, "count_active_admins", only_one)
    with TestClient(app) as client:
        response = client.post(f"/admin/users/{other_admin['id']}/deactivate")

    assert response.status_code == 409
    assert "dernier administrateur" in response.json()["detail"]


async def test_unknown_user_is_a_404(as_admin):
    with TestClient(app) as client:
        assert client.post("/admin/users/999999/deactivate").status_code == 404
