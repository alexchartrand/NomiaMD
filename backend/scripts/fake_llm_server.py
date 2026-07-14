"""A tiny fake OpenAI-compatible chat completions server, for testing and debugging the
extraction pipeline (and the frontend end-to-end) without a real local model.

Drop-in replacement for LocalAI: listens on the same host:port as NOMIAMD_BASE_URL's
default (http://localhost:8080/v1) — no .env changes needed. It's deliberately "dumb": it
parses the candidate RAMQ codes out of the prompt (built by
app/tasks/billing_codes.py::build_prompt) and picks a fixed number of them back, with
placeholder confidence/quote values. This exercises the whole pipeline (retrieval -> prompt
-> parse -> price lookup -> API -> frontend) deterministically, without depending on any
real model's behavior.

    python scripts/fake_llm_server.py [--port 8080] [--pick 2]
"""

import argparse
import json
import re
import time

from fastapi import FastAPI, Request

app = FastAPI(title="fake-llm")

_CANDIDATE_RE = re.compile(r"^- (?P<code>\S+): (?P<description>.+?) \(category: .+?\)$", re.MULTILINE)

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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    user_message = next((m["content"] for m in messages if m.get("role") == "user"), "")

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
