"""Shared LLM plumbing, talking to the Mistral API via llama-index's MistralAI client.
Task-specific logic lives entirely in app/tasks/* — adding a new output type never
requires touching this file."""

import json
import logging
import time
from functools import lru_cache
from typing import TypeVar

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.llms.mistralai import MistralAI

from app.config import settings
from app.extraction.models import ExtractionResult
from app.tasks.base import ExtractionTask

TInput = TypeVar("TInput")

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def get_client(model: str) -> MistralAI:
    """Cached per model name — a task with a stronger model= override
    (app/tasks/base.py's ExtractionTask.model) gets its own client instead of sharing one
    tuned for a different model."""
    return MistralAI(
        model=model,
        api_key=settings.mistral_api_key,
        # Deterministic on purpose: this is a structured extraction task (pick codes from a
        # closed candidate list), not a creative one — run-to-run variance here means the
        # same transcript can non-reproducibly get a code or not, which undermines both
        # debugging and the physician's trust in the suggestion.
        temperature=0,
        max_tokens=4096,
    )


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

    choice = response.raw["choices"][0]
    if choice.finish_reason not in ("stop", "length"):
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={choice.finish_reason!r})")

    raw = json.loads(response.message.content)
    parsed = task.parse(raw, prepared)

    return ExtractionResult(task=task.name, result=parsed, model=response.raw["model"])
