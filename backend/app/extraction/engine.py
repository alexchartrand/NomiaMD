"""Shared Claude API plumbing. Task-specific logic lives entirely in app/tasks/* —
adding a new output type never requires touching this file."""

import json
import os
from functools import lru_cache

import anthropic

from app.models import ExtractionResult
from app.tasks.base import ExtractionTask

MODEL = os.environ.get("NOMIAMD_MODEL") or "claude-opus-4-8"


@lru_cache(maxsize=1)
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def run_extraction(task: ExtractionTask, transcript: str) -> ExtractionResult:
    system_prompt, user_message = task.build_prompt(transcript)

    response = get_client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        thinking={"type": "adaptive"},
        output_config={
            "format": {"type": "json_schema", "schema": task.json_schema()}
        },
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this transcript (stop_reason=refusal)")

    text = next(block.text for block in response.content if block.type == "text")
    parsed = task.parse(json.loads(text))

    return ExtractionResult(task=task.name, result=parsed, model=response.model)
