"""Shared LLM plumbing, talking to whichever chat provider LLM_PROVIDER selects (see
app/llm/). Task-specific logic lives entirely in app/tasks/* — adding a new output type never
requires touching this file."""

import json
import logging
from typing import TypeVar

from pydantic import ValidationError

from app.config import settings
from app.extraction.models import ExtractionResult
from app.llm import ChatMessage, IChatClient, call_purpose, get_chat_client
from app.tasks.base import ExtractionTask

TInput = TypeVar("TInput")

logger = logging.getLogger(__name__)


class ExtractionOutputError(RuntimeError):
    """The model answered, but not with something the task can use: an abnormal
    `finish_reason`, no content, invalid JSON, or JSON the task's result model rejects. Carries
    the raw content so a parse failure can be inspected (and counted — smaller self-hosted
    models follow the strict schema less reliably)."""

    def __init__(self, message: str, *, raw_content: str | None, finish_reason: str | None):
        super().__init__(message)
        self.raw_content = raw_content
        self.finish_reason = finish_reason


def resolve_model(task: ExtractionTask | type[ExtractionTask], model: str | None = None) -> str:
    """Explicit argument, else the task's LLM_MODEL_<TASK> env override (a host whose model
    names differ from Mistral's), else the task's own default. Takes the task class too:
    only its `name` and `model` are read."""
    return model or settings.chat_model_for(task.name) or task.model


def get_client(model: str) -> IChatClient:
    """The seam tests patch (app.extraction.engine.get_client). Caching and the
    deterministic temperature=0 default live in get_chat_client."""
    return get_chat_client(model)


async def run_extraction(
    task: ExtractionTask[TInput], task_input: TInput, *, model: str | None = None
) -> ExtractionResult:
    prepared = await task.build_prompt(task_input)
    schema = task.json_schema()
    model = resolve_model(task, model)
    client = get_client(model)

    response_format = {
        "type": "json_schema",
        "json_schema": {"name": task.name, "strict": True, "schema": schema},
    }

    logger.debug(
        "run_extraction final query",
        extra={"task": task.name, "model": model, "user_message": prepared.user_message},
    )

    # Latency and token usage are metered per call by the client itself (app/llm/usage.py).
    with call_purpose(task.name):
        completion = await client.chat(
            messages=[
                ChatMessage(role="system", content=prepared.system_prompt),
                ChatMessage(role="user", content=prepared.user_message),
            ],
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
        parsed = task.parse(json.loads(completion.content), prepared)
    except (json.JSONDecodeError, ValidationError, TypeError, KeyError) as exc:
        raise ExtractionOutputError(
            f"Model output is not a valid {task.name} result ({type(exc).__name__}: {exc})",
            raw_content=completion.content,
            finish_reason=completion.finish_reason,
        ) from exc

    return ExtractionResult(task=task.name, result=parsed, model=completion.model)
