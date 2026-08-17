from typing import Literal

from pydantic import BaseModel


class RAMQChatMessage(BaseModel):
    """A single prior turn supplied by the client. No "system" role — the system prompt
    is fixed server-side, not client-controllable."""

    role: Literal["user", "assistant"]
    content: str


class RAMQQueryRequest(BaseModel):
    query: str
    history: list[RAMQChatMessage] = []


class RAMQQueryResult(BaseModel):
    answer: str
