"""Fakes for app/llm's client contracts, shared by the tests that mock the chat model
(patch("app.extraction.engine.get_client") with `.chat` returning fake_chat_result(...)) or
inject an embedding client."""

import json
from collections.abc import Sequence

from app.llm import ChatResult, IEmbeddingClient, TokenUsage


def fake_chat_result(payload, *, finish_reason: str = "stop", model: str = "mistral-small-latest") -> ChatResult:
    """A chat response whose content is `payload` (JSON-encoded unless already a string)."""
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return ChatResult(
        content=content,
        finish_reason=finish_reason,
        model=model,
        usage=TokenUsage(input_tokens=100, output_tokens=20),
        latency_ms=1.0,
    )


class FakeEmbeddingClient(IEmbeddingClient):
    """Exact text -> vector lookup (`default` for unknown texts), recording every batch."""

    def __init__(self, vectors: dict[str, list[float]] | None = None, *, default: list[float] | None = None, model_name: str = "fake-embed"):
        self._vectors = vectors or {}
        self._default = default if default is not None else [0.0]
        self._model_name = model_name
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors.get(text, self._default) for text in texts]
