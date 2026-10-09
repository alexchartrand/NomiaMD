"""The two client contracts the rest of the backend talks to. Callers depend on these, never
on an SDK: tests hand in fakes, the benchmark wraps an IEmbeddingClient in a disk cache, and
switching hosts is a provider change (app/llm/chat.py, app/llm/embeddings.py)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from app.llm.types import ChatMessage, ChatResult


class IChatClient(ABC):
    """One chat model at one temperature — both bound at construction, so a caller only
    supplies the conversation."""

    model: str

    @abstractmethod
    async def chat(
        self, messages: Sequence[ChatMessage], *, response_format: dict[str, Any] | None = None
    ) -> ChatResult:
        """`response_format` is OpenAI's structured-output shape
        (`{"type": "json_schema", "json_schema": {...}}`), forwarded as-is."""


class IEmbeddingClient(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """The EMBEDDING_PROVIDER that built it (`mistral`, `bedrock`...)."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    def identity(self) -> str:
        """`<provider>:<model>`, the name ramq-ingestion records on the tables it embeds
        (e.g. `mistral:mistral-embed`, `bedrock:cohere.embed-v4:0`) —
        app/llm/embedding_guard.py compares the two."""
        return f"{self.provider_name}:{self.model_name}"

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in input order, from a single call."""

    async def embed_query(self, text: str) -> list[float]:
        [vector] = await self.embed([text])
        return vector
