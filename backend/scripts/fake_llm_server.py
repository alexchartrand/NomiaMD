"""A tiny fake chat completions server, for testing and debugging the extraction
pipeline (and the frontend end-to-end) without calling the real Mistral API.

Speaks the same wire protocol app/extraction/engine.py's MistralAI client uses (POST
/v1/chat/completions, Mistral's own request/response shape). Point the app at it by
setting MISTRAL_ENDPOINT=http://localhost:8080 before starting the backend. It's
deliberately "dumb": it parses the candidate RAMQ codes out of the prompt (built by
app/ramq_codes/task.py::build_prompt) and picks a fixed number of them back, with
placeholder confidence/quote/fee values. This exercises the whole pipeline (retrieval ->
prompt -> parse -> API -> frontend) deterministically, without depending on any real
model's behavior.

    python scripts/fake_llm_server.py [--port 8080] [--pick 2]
"""

import argparse
import json
import re
import time

from fastapi import FastAPI, Request

app = FastAPI(title="fake-llm")

# Matches the "- CODE: description" prefix _format_candidate() always emits (see
# app/ramq_codes/task.py) — the rest of the line (when-to-use/conditions/fees
# brackets) is ignored, not part of this fake's stub output.
_CANDIDATE_RE = re.compile(r"^- (?P<code>\S+): (?P<description>[^\[]+?)(?: \[|$)", re.MULTILINE)

PICK = 2  # overridden by --pick at startup


def _fake_billing_codes_content(user_message: str) -> str:
    candidates = _CANDIDATE_RE.findall(user_message)
    chosen = candidates[:PICK]
    codes = [
        {
            "code": code,
            "description": description,
            "confidence": 0.5,
            "supporting_quote": "(stub quote — fake LLM, not a real extraction)",
            "fee": {"amount": None, "when_to_use": None, "majoration": None},
        }
        for code, description in chosen
    ]
    notes = (
        None
        if codes
        else "Fake LLM: no candidate codes were present in the prompt to pick from."
    )
    return json.dumps({"codes": codes, "notes": notes})


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": "fake-llm", "object": "model"}]}


def _content_to_text(content) -> str:
    """Message content is a bare string over the OpenAI wire format, but the Mistral
    client (llama_index's MistralAI) always sends it as a list of {"type": "text", ...}
    chunks instead — handle both."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict))
    return ""


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    user_message = _content_to_text(
        next((m["content"] for m in messages if m.get("role") == "user"), "")
    )

    content = _fake_billing_codes_content(user_message)

    return {
        "id": "fake-llm-0",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "fake-llm"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        # Required by mistralai's ChatCompletionResponse model, unused by the pipeline.
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--pick", type=int, default=2, help="How many candidate codes to echo back per request."
    )
    args = parser.parse_args()

    global PICK
    PICK = args.pick

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
