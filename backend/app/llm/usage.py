"""Per-call metering of every chat and embedding request: tokens in and out, latency, and what
the call was for. The SDK clients (app/llm/openai_client.py) report each call to a
UsageRecorder, which logs it as one structured `llm_call` line and hands it to every
usage_scope() open around the call.

Scopes and purposes are contextvars, so they follow the code that makes the call — through
awaits and into asyncio.gather children — without being threaded through every signature. Two
concurrent extractions each opening their own scope never see each other's calls: a task
copies its context when it's created, so a scope opened inside it is invisible to its
siblings."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)

CallKind = Literal["chat", "embedding"]


@dataclass(frozen=True)
class LLMCallRecord:
    kind: CallKind
    provider: str
    model: str
    purpose: str | None
    input_tokens: int | None
    # Always None for embeddings: they produce vectors, not tokens.
    output_tokens: int | None
    latency_ms: float
    started_at: datetime
    finish_reason: str | None = None
    # True when the benchmark's embedding cache answered instead of the provider: the token
    # counts are those of the original call, the latency is the cache's.
    cached: bool = False
    # Set on a call that raised (the exception's type and message); the tokens are then None.
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        return data


@dataclass
class UsageScope:
    """Collects every call recorded while it's open, in completion order."""

    records: list[LLMCallRecord] = field(default_factory=list)


_scopes: ContextVar[tuple[UsageScope, ...]] = ContextVar("llm_usage_scopes", default=())
_purpose: ContextVar[str | None] = ContextVar("llm_call_purpose", default=None)


@contextmanager
def usage_scope() -> Iterator[UsageScope]:
    scope = UsageScope()
    token = _scopes.set((*_scopes.get(), scope))
    try:
        yield scope
    finally:
        _scopes.reset(token)


@contextmanager
def call_purpose(purpose: str) -> Iterator[None]:
    """Tags the calls made inside with `purpose` (e.g. "consultation_summary",
    "billing_codes.retrieval"). The innermost purpose wins."""
    token = _purpose.set(purpose)
    try:
        yield
    finally:
        _purpose.reset(token)


def current_purpose() -> str | None:
    return _purpose.get()


class UsageRecorder:
    def record(self, call: LLMCallRecord) -> None:
        logger.info("llm_call", extra=call.to_dict())
        for scope in _scopes.get():
            scope.records.append(call)


default_recorder = UsageRecorder()
