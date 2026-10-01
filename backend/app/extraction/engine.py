"""Shared LLM plumbing, talking to whichever chat provider LLM_PROVIDER selects (see
app/llm/). Task-specific logic lives entirely in app/tasks/* — adding a new output type never
requires touching this file."""

import json
import logging
import time
from typing import TypeVar

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.llms import LLM

from app.extraction.models import ExtractionResult
from app.llm import ChatResponseReader, get_chat_llm
from app.tasks.base import ExtractionTask

TInput = TypeVar("TInput")

logger = logging.getLogger(__name__)


_reader = ChatResponseReader()


def get_client(model: str) -> LLM:
    """The seam tests patch (app.extraction.engine.get_client). Caching and the
    deterministic temperature=0 default live in get_chat_llm."""
    return get_chat_llm(model)


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

    llm_start = time.perf_counter()
    response = await client.achat(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content=prepared.system_prompt),
            ChatMessage(role=MessageRole.USER, content=prepared.user_message),
        ],
        response_format=response_format,
    )
    llm_duration_ms = (time.perf_counter() - llm_start) * 1000
    logger.debug(
        "run_extraction llm call timing",
        extra={"task": task.name, "model": task.model, "llm_duration_ms": round(llm_duration_ms, 1)},
    )

    completion = _reader.read(response)
    if completion.finish_reason not in ("stop", "length"):
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={completion.finish_reason!r})")

    raw = json.loads(completion.content)
    parsed = task.parse(raw, prepared)

    return ExtractionResult(task=task.name, result=parsed, model=completion.model)
