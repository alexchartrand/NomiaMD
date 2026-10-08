"""Shared LLM plumbing, talking to whichever chat provider LLM_PROVIDER selects (see
app/llm/). Task-specific logic lives entirely in app/tasks/* — adding a new output type never
requires touching this file."""

import json
import logging
from typing import TypeVar

from app.extraction.models import ExtractionResult
from app.llm import ChatMessage, IChatClient, call_purpose, get_chat_client
from app.tasks.base import ExtractionTask

TInput = TypeVar("TInput")

logger = logging.getLogger(__name__)


def get_client(model: str) -> IChatClient:
    """The seam tests patch (app.extraction.engine.get_client). Caching and the
    deterministic temperature=0 default live in get_chat_client."""
    return get_chat_client(model)


async def run_extraction(task: ExtractionTask[TInput], task_input: TInput) -> ExtractionResult:
    prepared = await task.build_prompt(task_input)
    schema = task.json_schema()
    client = get_client(task.model)

    response_format = {
        "type": "json_schema",
        "json_schema": {"name": task.name, "strict": True, "schema": schema},
    }

    logger.debug(
        "run_extraction final query",
        extra={"task": task.name, "model": task.model, "user_message": prepared.user_message},
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
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={completion.finish_reason!r})")

    raw = json.loads(completion.content)
    parsed = task.parse(raw, prepared)

    return ExtractionResult(task=task.name, result=parsed, model=completion.model)
