"""Shared LLM plumbing, talking to an OpenAI-compatible chat completions endpoint
(e.g. a local LocalAI instance). Task-specific logic lives entirely in app/tasks/* —
adding a new output type never requires touching this file."""

import json
import os
from functools import lru_cache

from openai import OpenAI

from app.models import ExtractionResult
from app.tasks.base import ExtractionTask

MODEL = os.environ.get("NOMIAMD_MODEL")
BASE_URL = os.environ.get("NOMIAMD_BASE_URL")


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    if not BASE_URL:
        raise RuntimeError("NOMIAMD_BASE_URL is not set — point it at your local model server's "
                            "OpenAI-compatible endpoint, e.g. http://localhost:8080/v1")
    # LocalAI usually doesn't check the key, but the client requires a non-empty string.
    return OpenAI(base_url=BASE_URL, api_key=os.environ.get("NOMIAMD_API_KEY") or "not-needed")


def run_extraction(task: ExtractionTask, transcript: str) -> ExtractionResult:
    system_prompt, user_message = task.build_prompt(transcript)

    response = get_client().chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": task.name, "schema": task.json_schema()},
        },
    )

    choice = response.choices[0]
    if choice.finish_reason not in ("stop", "length"):
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={choice.finish_reason!r})")

    parsed = task.parse(json.loads(choice.message.content))

    return ExtractionResult(task=task.name, result=parsed, model=response.model)
