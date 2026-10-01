"""One place for the raw-response shape differences between chat providers: llama-index's
MistralAI client hands back `raw` as a dict of SDK objects, OpenAILike hands back the
OpenAI SDK's ChatCompletion object itself. Callers read a ChatCompletion instead of
indexing `response.raw` directly."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from llama_index.core.base.llms.types import ChatResponse


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    finish_reason: str | None
    model: str


class ChatResponseReader:
    def read(self, response: ChatResponse) -> ChatCompletion:
        raw = response.raw
        choice = self._field(raw, "choices")[0]
        return ChatCompletion(
            content=response.message.content,
            finish_reason=self._field(choice, "finish_reason"),
            model=self._field(raw, "model"),
        )

    @staticmethod
    def _field(obj: Any, name: str) -> Any:
        return obj[name] if isinstance(obj, Mapping) else getattr(obj, name)
