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


def run_extraction(
    task: ExtractionTask, input_text: str) -> ExtractionResult:
    system_prompt, user_message = task.build_prompt(input_text)
    schema = task.json_schema()
    client = get_client()
    kwargs = {}

    kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": task.name, "strict": True, "schema": schema}}

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        # Deterministic on purpose: this is a structured extraction task (pick codes from a
        # closed candidate list), not a creative one — run-to-run variance here means the
        # same transcript can non-reproducibly get a code or not, which undermines both
        # debugging and the physician's trust in the suggestion.
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        **kwargs,
    )

    choice = response.choices[0]
    if choice.finish_reason not in ("stop", "length"):
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={choice.finish_reason!r})")

    raw = json.loads(choice.message.content)
    parsed = task.parse(raw)

    return ExtractionResult(task=task.name, result=parsed, model=response.model)
