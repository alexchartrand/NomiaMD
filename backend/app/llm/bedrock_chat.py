"""Chat on Amazon Bedrock through the Converse API, so any Bedrock text model (Claude, Mistral,
gpt-oss, Qwen...) can run the extraction tasks. Bedrock's OpenAI-compatible endpoints don't
take a strict JSON schema for every model (Claude rejects it there), while Converse takes one
for all of them as `outputConfig.textFormat` — so, like Bedrock's embeddings (bedrock.py),
chat goes through boto3 instead of app/llm/openai_client.py.

Callers keep speaking the OpenAI shapes IChatClient defines: ConverseRequestBuilder turns the
messages and `response_format` into a Converse request, and ConverseResponseReader turns the
answer back into a ChatResult, with Bedrock's stop reasons mapped onto OpenAI's
`finish_reason` values (the extraction engine accepts `stop` and `length`).

Credentials come from the AWS SDK's own chain (`aws login`), never from settings. Chat
messages carry PHI: only synthetic notes may go to Bedrock until the hosting Region is
cleared for real data."""

import asyncio
import json
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.llm.bedrock import bedrock_runtime_client
from app.llm.client import IChatClient
from app.llm.openai_client import MAX_TOKENS
from app.llm.provider import ChatModelProvider
from app.llm.types import ChatMessage, ChatResult, TokenUsage
from app.llm.usage import LLMCallRecord, UsageRecorder, current_purpose, default_recorder

# Converse's stopReason → OpenAI's finish_reason. Any other reason (guardrail_intervened,
# content_filtered, tool_use...) is passed through as-is, which the engine rejects.
_FINISH_REASONS = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length"}


class ConverseRequestBuilder:
    """The Converse request for one chat call: system messages go to `system`, the rest to
    `messages`, and an OpenAI `json_schema` response format to `outputConfig.textFormat`
    (whose schema Converse takes as a JSON string)."""

    def build(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "modelId": model,
            "messages": [{"role": m.role, "content": [{"text": m.content}]} for m in messages if m.role != "system"],
            "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
        }
        system = [{"text": m.content} for m in messages if m.role == "system"]
        if system:
            request["system"] = system
        if response_format is not None:
            request["outputConfig"] = {"textFormat": self._text_format(response_format)}
        return request

    def _text_format(self, response_format: dict[str, Any]) -> dict[str, Any]:
        if response_format.get("type") != "json_schema":
            raise ValueError(f"Bedrock Converse only takes a json_schema response format, got {response_format.get('type')!r}")
        spec = response_format["json_schema"]
        return {
            "type": "json_schema",
            "structure": {"jsonSchema": {"name": spec["name"], "schema": json.dumps(spec["schema"])}},
        }


class ConverseResponseReader:
    """The text, finish reason and token counts of a Converse response. Reasoning models
    (gpt-oss, Qwen) put their reasoning in `reasoningContent` blocks before the answer: only
    the `text` blocks are the answer.

    Bedrock doesn't hold gpt-oss to the schema on long prompts: its answer can start with a
    leaked reasoning-channel marker (`**analysis{...}`, `**{...}`) before otherwise valid
    JSON. When a JSON answer was asked for, whatever surrounds the outermost object is that
    leak and is cut; the caller still validates what's left."""

    def content(self, response: dict[str, Any], *, json_expected: bool = False) -> str | None:
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        texts = [block["text"] for block in blocks if "text" in block]
        if not texts:
            return None
        text = "".join(texts)
        return self._outermost_object(text) if json_expected else text

    @staticmethod
    def _outermost_object(text: str) -> str:
        start, end = text.find("{"), text.rfind("}")
        return text[start : end + 1] if 0 <= start < end else text

    def finish_reason(self, response: dict[str, Any]) -> str | None:
        reason = response.get("stopReason")
        return _FINISH_REASONS.get(reason, reason)

    def usage(self, response: dict[str, Any]) -> TokenUsage:
        usage = response.get("usage", {})
        return TokenUsage(input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"))


class BedrockChatClient(IChatClient):
    """`client` is a boto3 `bedrock-runtime` client. boto3 is synchronous, so each call runs
    in a worker thread; its clients are thread-safe."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        temperature: float,
        max_tokens: int = MAX_TOKENS,
        request_builder: ConverseRequestBuilder | None = None,
        response_reader: ConverseResponseReader | None = None,
        recorder: UsageRecorder = default_recorder,
    ):
        self._client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._request_builder = request_builder or ConverseRequestBuilder()
        self._response_reader = response_reader or ConverseResponseReader()
        self._recorder = recorder

    async def chat(
        self, messages: Sequence[ChatMessage], *, response_format: dict[str, Any] | None = None
    ) -> ChatResult:
        request = self._request_builder.build(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format=response_format,
        )
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            response = await asyncio.to_thread(self._client.converse, **request)
        except Exception as exc:
            self._record(started_at, start, TokenUsage(), None, error=f"{type(exc).__name__}: {exc}")
            raise

        latency_ms = (time.perf_counter() - start) * 1000
        usage = self._response_reader.usage(response)
        finish_reason = self._response_reader.finish_reason(response)
        self._record(started_at, start, usage, finish_reason)
        return ChatResult(
            content=self._response_reader.content(response, json_expected=response_format is not None),
            finish_reason=finish_reason,
            model=self.model,
            usage=usage,
            latency_ms=latency_ms,
        )

    def _record(
        self,
        started_at: datetime,
        start: float,
        usage: TokenUsage,
        finish_reason: str | None,
        *,
        error: str | None = None,
    ) -> None:
        self._recorder.record(
            LLMCallRecord(
                kind="chat",
                provider=BedrockChatProvider.name,
                model=self.model,
                purpose=current_purpose(),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=(time.perf_counter() - start) * 1000,
                started_at=started_at,
                finish_reason=finish_reason,
                error=error,
            )
        )


class BedrockChatProvider(ChatModelProvider):
    """Amazon Bedrock's Converse API. The model is a Bedrock model or inference profile id
    (e.g. `us.anthropic.claude-sonnet-5-5`, `openai.gpt-oss-120b-1:0`), set per call with
    LLM_MODEL_<TASK> or the benchmark's --selection-model. BEDROCK_REGION overrides the
    Region the AWS SDK's own configuration picks. LLM_API_KEY and LLM_ENDPOINT are unused."""

    name = "bedrock"

    def build(self, model: str, temperature: float) -> IChatClient:
        return BedrockChatClient(bedrock_runtime_client(settings.bedrock_region), model=model, temperature=temperature)
