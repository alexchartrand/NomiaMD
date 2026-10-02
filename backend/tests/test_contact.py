"""POST /contact: the public site's contact form — saved, notified best-effort after the
response, refused without Law 25 consent, silently dropped when the honeypot is filled."""

import itertools

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.contact.factory import get_contact_notifier
from app.contact.models import ContactRequestIn
from app.contact.notifier import ContactNotifier, SmtpContactNotifier
from app.main import app
from app.postgresdb import ContactRequest, ContactRole, ContactTopic, session_scope

# The test DB is shared across the session, so each test tags its rows with its own email.
_emails = (f"prospect{n}@clinique-exemple.ca" for n in itertools.count(1))


class RecordingNotifier(ContactNotifier):
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[int, ContactRequestIn]] = []
        self._fail = fail

    async def _send(self, request_id: int, form: ContactRequestIn) -> None:
        if self._fail:
            raise RuntimeError("SMTP down")
        self.sent.append((request_id, form))


@pytest.fixture
def notifier():
    recording = RecordingNotifier()
    app.dependency_overrides[get_contact_notifier] = lambda: recording
    yield recording
    app.dependency_overrides.pop(get_contact_notifier, None)


def _form(email: str, **overrides) -> dict:
    return {
        "name": "Dre Julie Tremblay",
        "email": email,
        "phone": "514-555-0101",
        "organization": "GMF du Plateau",
        "role": "medecin",
        "physician_count": 8,
        "topic": "tarifs",
        "plan": "clinique",
        "message": "Nous aimerions une démo.",
        "consent": True,
        **overrides,
    }


async def _rows_for(email: str) -> list[ContactRequest]:
    async with session_scope() as session:
        return list((await session.scalars(select(ContactRequest).where(ContactRequest.email == email))).all())


async def test_submit_saves_the_request_and_notifies(notifier):
    email = next(_emails)
    with TestClient(app) as client:
        response = client.post("/contact", json=_form(email))

    assert response.status_code == 204
    [row] = await _rows_for(email)
    assert row.name == "Dre Julie Tremblay"
    assert row.role is ContactRole.PHYSICIAN
    assert row.topic is ContactTopic.PRICING
    assert row.plan == "clinique"
    assert row.physician_count == 8
    assert row.consent_at is not None
    assert [(request_id, form.email) for request_id, form in notifier.sent] == [(row.id, email)]


async def test_optional_fields_may_be_blank(notifier):
    email = next(_emails)
    with TestClient(app) as client:
        response = client.post(
            "/contact",
            json={"name": "Alex", "email": email, "role": "partenaire", "phone": "  ", "message": "", "consent": True},
        )

    assert response.status_code == 204
    [row] = await _rows_for(email)
    assert row.topic is ContactTopic.DEMO
    assert row.phone is None
    assert row.message is None


@pytest.mark.parametrize("consent", [False, None])
async def test_submit_without_consent_is_refused(notifier, consent):
    email = next(_emails)
    form = _form(email, consent=consent)
    if consent is None:
        del form["consent"]
    with TestClient(app) as client:
        response = client.post("/contact", json=form)

    assert response.status_code == 422
    assert await _rows_for(email) == []
    assert notifier.sent == []


async def test_newline_in_a_single_line_field_is_refused(notifier):
    email = next(_emails)
    with TestClient(app) as client:
        response = client.post("/contact", json=_form(email, name="Alex\r\nBcc: someone@example.test"))

    assert response.status_code == 422
    assert await _rows_for(email) == []


async def test_honeypot_is_accepted_but_dropped(notifier):
    email = next(_emails)
    with TestClient(app) as client:
        response = client.post("/contact", json=_form(email, website="http://spam.test"))

    assert response.status_code == 204
    assert await _rows_for(email) == []
    assert notifier.sent == []


async def test_notification_failure_still_saves_and_succeeds():
    failing = RecordingNotifier(fail=True)
    app.dependency_overrides[get_contact_notifier] = lambda: failing
    email = next(_emails)
    try:
        with TestClient(app) as client:
            response = client.post("/contact", json=_form(email))
    finally:
        app.dependency_overrides.pop(get_contact_notifier, None)

    assert response.status_code == 204
    assert len(await _rows_for(email)) == 1


async def test_rate_limited_after_five_requests_an_hour(notifier):
    with TestClient(app) as client:
        statuses = [client.post("/contact", json=_form(next(_emails))).status_code for _ in range(6)]

    assert statuses == [204] * 5 + [429]


def test_smtp_message_replies_to_the_prospect():
    smtp = SmtpContactNotifier(
        host="smtp.test", port=587, sender="noreply@nomiamd-exemple.ca", recipient="contact@nomiamd-exemple.ca"
    )
    form = ContactRequestIn.model_validate(_form("julie@clinique-exemple.ca"))

    message = smtp.build_message(42, form)

    assert message["To"] == "contact@nomiamd-exemple.ca"
    assert message["Reply-To"] == "julie@clinique-exemple.ca"
    assert "#42" in message["Subject"]
    body = message.get_content()
    assert "GMF du Plateau" in body
    assert "Médecin" in body
    assert "Nous aimerions une démo." in body
