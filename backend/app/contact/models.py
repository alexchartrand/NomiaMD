"""Contact-form request model — the frontend copy lives in frontend/src/api/contact.ts."""

from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

from app.postgresdb import ContactRole, ContactTopic

# Single-line fields end up in the notification email; a newline there is never legitimate.
SingleLine = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[^\r\n]*$")]


class ContactRequestIn(BaseModel):
    name: Annotated[SingleLine, StringConstraints(min_length=1, max_length=120)]
    email: EmailStr
    phone: Annotated[SingleLine, StringConstraints(max_length=40)] | None = None
    organization: Annotated[SingleLine, StringConstraints(max_length=160)] | None = None
    role: ContactRole
    physician_count: Annotated[int, Field(ge=1, le=10_000)] | None = None
    topic: ContactTopic = ContactTopic.DEMO
    plan: Annotated[str, StringConstraints(pattern=r"^[a-z-]{1,32}$")] | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None
    # The Law 25 consent box: the request is refused unless it was ticked.
    consent: Literal[True]
    # Honeypot: hidden from people by the form, so only bots fill it in.
    website: str | None = None

    @field_validator("phone", "organization", "message", mode="after")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def is_spam(self) -> bool:
        return bool(self.website)
