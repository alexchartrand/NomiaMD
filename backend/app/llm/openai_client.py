"""The only module that talks to an SDK. Every host this backend uses speaks the OpenAI wire
protocol — Mistral's API, vLLM, TEI, the fake dev server — so one adapter per call kind covers
them all; the providers (app/llm/mistral.py, app/llm/openai_compatible.py) only differ in the
base URL and key they hand it.

Each call is timed and reported to a UsageRecorder (app/llm/usage.py) with the token counts
the response carries, failed calls included."""

import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from openai import AsyncOpenAI

from app.llm.client import IChatClient, IEmbeddingClient
from app.llm.types import ChatMessage, ChatResult, TokenUsage
from app.llm.usage import LLMCallRecord, UsageRecorder, current_purpose, default_recorder

# Applied to every chat call: structured extraction outputs (the billing_codes JSON in
# particular) can be long, and a truncated completion is unparseable.
MAX_TOKENS = 4096


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class OpenAIChatClient(IChatClient):
    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int = MAX_TOKENS,
        recorder: UsageRecorder = default_recorder,
    ):
        self._client = client
        self._provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._recorder = recorder

    async def chat(
        self, messages: Sequence[ChatMessage], *, response_format: dict[str, Any] | None = None
    ) -> ChatResult:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if response_format is not None:
            request["response_format"] = response_format

        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(**request)
        except Exception as exc:
            self._record(started_at, _elapsed_ms(start), TokenUsage(), None, self.model, error=_error_text(exc))
            raise

        latency_ms = _elapsed_ms(start)
        usage = TokenUsage(
            input_tokens=getattr(response.usage, "prompt_tokens", None),
            output_tokens=getattr(response.usage, "completion_tokens", None),
        )
        choice = response.choices[0]
        model = response.model or self.model
        self._record(started_at, latency_ms, usage, choice.finish_reason, model)
        return ChatResult(
            content=choice.message.content,
            finish_reason=choice.finish_reason,
            model=model,
            usage=usage,
            latency_ms=latency_ms,
        )

    def _record(
        self,
        started_at: datetime,
        latency_ms: float,
        usage: TokenUsage,
        finish_reason: str | None,
        model: str,
        *,
        error: str | None = None,
    ) -> None:
        self._recorder.record(
            LLMCallRecord(
                kind="chat",
                provider=self._provider,
                model=model,
                purpose=current_purpose(),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=latency_ms,
                started_at=started_at,
                finish_reason=finish_reason,
                error=error,
            )
        )


class OpenAIEmbeddingClient(IEmbeddingClient):
    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        provider: str,
        model: str,
        recorder: UsageRecorder = default_recorder,
    ):
        self._client = client
        self._provider = provider
        self._model = model
        self._recorder = recorder

    @property
    def model_name(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            # "float" explicitly: the SDK otherwise asks for base64, which not every
            # OpenAI-compatible server (Mistral, TEI) serves.
            response = await self._client.embeddings.create(
                model=self._model, input=list(texts), encoding_format="float"
            )
        except Exception as exc:
            self._record(started_at, _elapsed_ms(start), input_tokens=None, error=_error_text(exc))
            raise

        self._record(started_at, _elapsed_ms(start), input_tokens=getattr(response.usage, "prompt_tokens", None))
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def _record(
        self, started_at: datetime, latency_ms: float, *, input_tokens: int | None, error: str | None = None
    ) -> None:
        self._recorder.record(
            LLMCallRecord(
                kind="embedding",
                provider=self._provider,
                model=self._model,
                purpose=current_purpose(),
                input_tokens=input_tokens,
                output_tokens=None,
                latency_ms=latency_ms,
                started_at=started_at,
                error=error,
            )
        )
