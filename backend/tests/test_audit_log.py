"""The account trail: login attempts on real accounts land in audit_events even when the
request itself is rolled back (a 401), and unknown emails leave no row."""

import uuid

from fastapi.testclient import TestClient

from app.audit import AuditAction, AuditEntry, DetachedAuditLog, SessionAuditLog
from app.main import app
from app.postgresdb import AuditEventFilter, AuditEventRepository, session_scope
from tests.test_auth import PASSWORD, _create_user, _drop_auth_override


async def _events_for(user_id: int):
    async with session_scope() as session:
        return await AuditEventRepository(session).list(AuditEventFilter(user_id=user_id))


async def test_successful_login_is_recorded():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    [event] = await _events_for(user.id)
    assert event.action == AuditAction.LOGIN_SUCCEEDED.value
    assert event.actor_id == user.id
    assert event.ip == "testclient"


async def test_failed_login_is_recorded_despite_the_rolled_back_request():
    _drop_auth_override()
    user = await _create_user()

    with TestClient(app) as client:
        response = client.post("/auth/login", json={"email": user.email, "password": "wrong password"})

    assert response.status_code == 401
    [event] = await _events_for(user.id)
    assert event.action == AuditAction.LOGIN_FAILED.value
    assert event.details == {"reason": "bad_password"}
    assert event.actor_id is None


async def test_unknown_email_leaves_no_event():
    _drop_auth_override()
    email = f"nobody-{uuid.uuid4().hex[:8]}@example.test"
    async with session_scope() as session:
        before = len(await AuditEventRepository(session).list(limit=200))

    with TestClient(app) as client:
        client.post("/auth/login", json={"email": email, "password": PASSWORD})

    async with session_scope() as session:
        after = len(await AuditEventRepository(session).list(limit=200))
    assert after == before


async def test_session_audit_log_rolls_back_with_its_transaction():
    user = await _create_user()

    try:
        async with session_scope() as session:
            await SessionAuditLog(session).record(AuditEntry(AuditAction.USER_UPDATED, target_user_id=user.id))
            raise RuntimeError("the change failed")
    except RuntimeError:
        pass

    assert await _events_for(user.id) == []


async def test_detached_audit_log_filters_by_action():
    user = await _create_user()
    await DetachedAuditLog().record(AuditEntry(AuditAction.USER_DEACTIVATED, target_user_id=user.id))
    await DetachedAuditLog().record(AuditEntry(AuditAction.USER_REACTIVATED, target_user_id=user.id))

    async with session_scope() as session:
        events = await AuditEventRepository(session).list(
            AuditEventFilter(user_id=user.id, action=AuditAction.USER_DEACTIVATED.value)
        )
    assert [e.action for e in events] == [AuditAction.USER_DEACTIVATED.value]
