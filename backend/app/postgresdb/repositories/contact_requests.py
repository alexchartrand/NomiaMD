"""`contact_requests` — messages from the public site's contact form."""

from dataclasses import dataclass

from app.postgresdb.models import ContactRequest, ContactRole, ContactTopic
from app.postgresdb.repositories.base import SessionRepository


@dataclass
class ContactRequestInput:
    name: str
    email: str
    role: ContactRole
    topic: ContactTopic
    phone: str | None = None
    organization: str | None = None
    physician_count: int | None = None
    plan: str | None = None
    message: str | None = None


class ContactRequestRepository(SessionRepository):
    """Stores contact requests — write-only for now; they're read straight from the DB
    until there's an admin screen."""

    async def create(self, data: ContactRequestInput) -> ContactRequest:
        contact_request = ContactRequest(
            name=data.name,
            email=data.email,
            phone=data.phone,
            organization=data.organization,
            role=data.role,
            physician_count=data.physician_count,
            topic=data.topic,
            plan=data.plan,
            message=data.message,
        )
        self._session.add(contact_request)
        await self._session.flush()
        return contact_request
