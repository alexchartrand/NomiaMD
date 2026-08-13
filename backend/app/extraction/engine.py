"""Shared LLM plumbing, talking to the Mistral API via llama-index's MistralAI client.
Task-specific logic lives entirely in app/tasks/* — adding a new output type never
requires touching this file."""

import json
import os
from functools import lru_cache

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.llms.mistralai import MistralAI

from app.models import ExtractionResult
from app.tasks.base import ExtractionTask

MODEL = "mistral-small-latest"


@lru_cache(maxsize=1)
def get_client() -> MistralAI:
    return MistralAI(
        model=MODEL,
        api_key=os.environ["MISTRAL_API_KEY"],
        # Deterministic on purpose: this is a structured extraction task (pick codes from a
        # closed candidate list), not a creative one — run-to-run variance here means the
        # same transcript can non-reproducibly get a code or not, which undermines both
        # debugging and the physician's trust in the suggestion.
        temperature=0,
        max_tokens=4096,
    )


def run_extraction(
    task: ExtractionTask, input_text: str) -> ExtractionResult:
    system_prompt, user_message = task.build_prompt(input_text)
    schema = task.json_schema()
    client = get_client()

    response_format = {
        "type": "json_schema",
        "json_schema": {"name": task.name, "strict": True, "schema": schema},
    }

    response = client.chat(
        messages=[
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_message),
        ],
        response_format=response_format,
    )

    choice = response.raw["choices"][0]
    if choice.finish_reason not in ("stop", "length"):
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={choice.finish_reason!r})")

    raw = json.loads(response.message.content)
    parsed = task.parse(raw)

    return ExtractionResult(task=task.name, result=parsed, model=response.raw["model"])
