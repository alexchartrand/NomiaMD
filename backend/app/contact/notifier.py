"""Tells the team a contact request came in. Best effort by design: the request is already
saved when this runs (after the response, from BackgroundTasks), so a mail failure is
logged and never surfaces to the person who filled in the form."""

import asyncio
import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from app.contact.models import ContactRequestIn

logger = logging.getLogger(__name__)

_ROLE_LABELS = {
    "medecin": "Médecin",
    "gestionnaire": "Gestionnaire de clinique",
    "partenaire": "Partenaire / fournisseur",
    "autre": "Autre",
}
_TOPIC_LABELS = {
    "demo": "Démo",
    "essai": "Essai gratuit",
    "tarifs": "Tarifs",
    "partenariat": "Partenariat",
    "autre": "Autre",
}


class ContactNotifier(ABC):
    async def notify(self, request_id: int, form: ContactRequestIn) -> None:
        try:
            await self._send(request_id, form)
        except Exception:
            logger.exception("Contact request %s saved but its notification failed", request_id)

    @abstractmethod
    async def _send(self, request_id: int, form: ContactRequestIn) -> None: ...


class LogContactNotifier(ContactNotifier):
    """Used when SMTP isn't configured (local dev, tests) — the row is in the DB either way.
    Logs the id and topic only, not the person's details."""

    async def _send(self, request_id: int, form: ContactRequestIn) -> None:
        logger.info("New contact request %s (topic=%s)", request_id, form.topic.value)


class SmtpContactNotifier(ContactNotifier):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipient: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._recipient = recipient
        self._username = username
        self._password = password

    async def _send(self, request_id: int, form: ContactRequestIn) -> None:
        await asyncio.to_thread(self._send_blocking, self.build_message(request_id, form))

    def build_message(self, request_id: int, form: ContactRequestIn) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = f"[NomiaMD] Nouvelle demande — {_TOPIC_LABELS[form.topic.value]} (#{request_id})"
        message["From"] = self._sender
        message["To"] = self._recipient
        message["Reply-To"] = form.email
        lines = [
            f"Nom : {form.name}",
            f"Courriel : {form.email}",
            f"Téléphone : {form.phone or '—'}",
            f"Organisation : {form.organization or '—'}",
            f"Rôle : {_ROLE_LABELS[form.role.value]}",
            f"Nombre de médecins : {form.physician_count or '—'}",
            f"Sujet : {_TOPIC_LABELS[form.topic.value]}",
            f"Forfait : {form.plan or '—'}",
            "",
            form.message or "(aucun message)",
        ]
        message.set_content("\n".join(lines))
        return message

    def _send_blocking(self, message: EmailMessage) -> None:
        if self._port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(self._host, self._port, timeout=15)
        else:
            client = smtplib.SMTP(self._host, self._port, timeout=15)
            client.starttls()
        with client:
            if self._username and self._password:
                client.login(self._username, self._password)
            client.send_message(message)
