"""`contact_requests` — messages from the public site's contact form."""

from dataclasses import dataclass

from sqlalchemy import select

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
    """Stores contact requests; the admin console lists them."""

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[ContactRequest]:
        result = await self._session.execute(
            select(ContactRequest)
            .order_by(ContactRequest.created_at.desc(), ContactRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

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
