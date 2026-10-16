"""One structured chat call: a system prompt and a user message in, JSON matching a Pydantic
model's strict schema out, on whichever chat provider LLM_PROVIDER selects. Shared by
ConsultationSummarizer (app/summary/) and CodeSelector (app/ramq_codes/), which build their
own prompts and parse the reply themselves."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.llm.chat import get_chat_client
from app.llm.client import IChatClient
from app.llm.schema import to_strict_schema
from app.llm.types import ChatMessage
from app.llm.usage import call_purpose

T = TypeVar("T")

logger = logging.getLogger(__name__)


class ExtractionOutputError(RuntimeError):
    """The model answered, but not with something the caller can use: an abnormal
    `finish_reason`, no content, invalid JSON, or JSON the result model rejects. Carries the
    raw content so a parse failure can be inspected (and counted — smaller self-hosted models
    follow the strict schema less reliably)."""

    def __init__(self, message: str, *, raw_content: str | None, finish_reason: str | None):
        super().__init__(message)
        self.raw_content = raw_content
        self.finish_reason = finish_reason


def resolve_model(name: str, default: str, model: str | None = None) -> str:
    """Explicit argument, else the call's LLM_MODEL_<NAME> env override (a host whose model
    names differ from Mistral's), else its own default."""
    return model or settings.chat_model_for(name) or default


def get_client(model: str) -> IChatClient:
    """The seam tests patch (app.llm.structured.get_client). Caching and the deterministic
    temperature=0 default live in get_chat_client."""
    return get_chat_client(model)


@dataclass(frozen=True)
class StructuredReply:
    """The model's JSON answer, not yet validated. `model` is the id the provider reports
    (e.g. a dated snapshot), not necessarily the one requested."""

    name: str
    raw: Any
    content: str
    finish_reason: str | None
    model: str

    def parse_with(self, parse: Callable[[Any], T]) -> T:
        """Runs `parse` on the raw JSON; a result the model got wrong becomes an
        ExtractionOutputError carrying the raw content."""
        try:
            return parse(self.raw)
        except (ValidationError, TypeError, KeyError) as exc:
            raise _invalid_output(self.name, self.content, self.finish_reason, exc) from exc


def _invalid_output(name: str, content: str, finish_reason: str | None, exc: Exception) -> ExtractionOutputError:
    return ExtractionOutputError(
        f"Model output is not a valid {name} result ({type(exc).__name__}: {exc})",
        raw_content=content,
        finish_reason=finish_reason,
    )


class StructuredChat:
    async def complete(
        self, *, name: str, model: str, system: str, user: str, output: type[BaseModel]
    ) -> StructuredReply:
        """`name` names the call: the response schema, the metered call's purpose and the
        error messages. `output` is the model whose strict schema the answer must match."""
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": to_strict_schema(output)},
        }
        logger.debug("structured chat final query", extra={"call": name, "model": model, "user_message": user})

        # Latency and token usage are metered per call by the client itself (app/llm/usage.py).
        with call_purpose(name):
            completion = await get_client(model).chat(
                messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
                response_format=response_format,
            )

        if completion.finish_reason not in ("stop", "length"):
            raise ExtractionOutputError(
                f"Model did not return a normal completion (finish_reason={completion.finish_reason!r})",
                raw_content=completion.content,
                finish_reason=completion.finish_reason,
            )
        if completion.content is None:
            raise ExtractionOutputError(
                "Model returned no content", raw_content=None, finish_reason=completion.finish_reason
            )

        try:
            raw = json.loads(completion.content)
        except json.JSONDecodeError as exc:
            raise _invalid_output(name, completion.content, completion.finish_reason, exc) from exc
        return StructuredReply(
            name=name, raw=raw, content=completion.content, finish_reason=completion.finish_reason, model=completion.model
        )
