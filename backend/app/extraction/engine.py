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

# Small local models tend to collapse to a trivial-but-valid empty response (e.g.
# {"codes": [], ...} in a handful of tokens) when decoding is grammar-constrained to the
# JSON schema — the constraint enforces validity, not reasoning, and weak models take the
# shortest valid way out. Set NOMIAMD_STRUCTURED_OUTPUT=false to fall back to freeform
# generation (schema described in the prompt instead of enforced), which gives the model
# room to actually reason before committing to output. Re-enable once running a model
# capable enough to reason under the grammar constraint.
STRUCTURED_OUTPUT = (os.environ.get("NOMIAMD_STRUCTURED_OUTPUT") or "true").lower() not in (
    "false", "0", "no",
)


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    if not BASE_URL:
        raise RuntimeError("NOMIAMD_BASE_URL is not set — point it at your local model server's "
                            "OpenAI-compatible endpoint, e.g. http://localhost:8080/v1")
    # LocalAI usually doesn't check the key, but the client requires a non-empty string.
    return OpenAI(base_url=BASE_URL, api_key=os.environ.get("NOMIAMD_API_KEY") or "not-needed")


def _extract_json(text: str) -> dict:
    """Freeform models sometimes wrap JSON in code fences or a stray sentence despite
    being told not to — pull out the outermost {...} object rather than assuming the
    whole response is clean JSON."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Model response did not contain a JSON object: {text!r}")
    return json.loads(text[start : end + 1])


def run_extraction(task: ExtractionTask, transcript: str) -> ExtractionResult:
    system_prompt, user_message = task.build_prompt(transcript)
    schema = task.json_schema()

    kwargs = {}
    if STRUCTURED_OUTPUT:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": task.name, "schema": schema},
        }
    else:
        system_prompt += (
            "\n\nRespond with a single JSON object only (no markdown code fences, no other "
            "text) matching exactly this JSON schema:\n" + json.dumps(schema)
        )

    response = get_client().chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        **kwargs,
    )

    choice = response.choices[0]
    if choice.finish_reason not in ("stop", "length"):
        raise RuntimeError(f"Model did not return a normal completion (finish_reason={choice.finish_reason!r})")

    raw = json.loads(choice.message.content) if STRUCTURED_OUTPUT else _extract_json(choice.message.content)
    parsed = task.parse(raw)

    return ExtractionResult(task=task.name, result=parsed, model=response.model)
