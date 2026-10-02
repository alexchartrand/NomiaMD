"""Saves contact-form requests. Notifying anyone is the router's job (after the response),
not this service's."""

from app.contact.models import ContactRequestIn
from app.postgresdb import ContactRequest, ContactRequestInput, ContactRequestRepository


class ContactService:
    def __init__(self, requests: ContactRequestRepository) -> None:
        self._requests = requests

    async def submit(self, form: ContactRequestIn) -> ContactRequest | None:
        """The saved request, or None when the honeypot caught a bot — which still gets the
        same success response, so it learns nothing."""
        if form.is_spam:
            return None
        return await self._requests.create(
            ContactRequestInput(
                name=form.name,
                email=form.email,
                phone=form.phone,
                organization=form.organization,
                role=form.role,
                physician_count=form.physician_count,
                topic=form.topic,
                plan=form.plan,
                message=form.message,
            )
        )
