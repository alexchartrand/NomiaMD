"""The provider-neutral shapes every chat/embedding caller works in. Nothing here knows which
SDK or host produced a response — app/llm/openai_client.py is the only module that does."""

from dataclasses import dataclass
from typing import Literal

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class TokenUsage:
    """Token counts as the provider reported them. None when the provider omitted them
    (some OpenAI-compatible servers don't send `usage`), never an estimate."""

    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ChatResult:
    # None when the model returned no message content at all (callers decide whether that's
    # an error — it is for both structured extraction and the chatbot).
    content: str | None
    finish_reason: str | None
    model: str
    usage: TokenUsage
    latency_ms: float
