"""Composition root for the contact form — wires the service over the request's session and
picks the notifier from settings."""

from app.config import settings
from app.contact.notifier import ContactNotifier, LogContactNotifier, SmtpContactNotifier
from app.contact.service import ContactService
from app.postgresdb import ContactRequestRepository, DbSession


def get_contact_service(session: DbSession) -> ContactService:
    return ContactService(ContactRequestRepository(session))


def get_contact_notifier() -> ContactNotifier:
    host, sender, recipient = settings.smtp_host, settings.smtp_from, settings.contact_notify_email
    if host is None or sender is None or recipient is None:
        return LogContactNotifier()
    return SmtpContactNotifier(
        host=host,
        port=settings.smtp_port,
        sender=sender,
        recipient=recipient,
        username=settings.smtp_username,
        password=settings.smtp_password,
    )
