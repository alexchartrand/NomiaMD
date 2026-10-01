"""Builds the configured chat LLM. LLM_PROVIDER picks the backend; every caller (extraction
engine, ramq_chatbot) goes through get_chat_llm so none of them names a provider."""

from functools import lru_cache

from llama_index.core.llms import LLM

from app.config import settings
from app.llm.mistral import MistralChatProvider
from app.llm.openai_compatible import OpenAICompatibleChatProvider
from app.llm.provider import ChatModelProvider

_PROVIDERS: dict[str, type[ChatModelProvider]] = {
    "mistral": MistralChatProvider,
    "openai_compatible": OpenAICompatibleChatProvider,
}


class UnknownChatProviderError(ValueError):
    pass


def chat_provider() -> ChatModelProvider:
    """The provider LLM_PROVIDER names. Called from app/bootstrap.py at startup so a typo
    fails the boot instead of the first extraction."""
    name = settings.llm_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownChatProviderError(
            f"Unknown LLM_PROVIDER={name!r}; expected one of {sorted(_PROVIDERS)}"
        ) from None


@lru_cache(maxsize=None)
def get_chat_llm(model: str, temperature: float = 0.0) -> LLM:
    """Cached per (model, temperature) — a task with a stronger model= override
    (app/tasks/base.py's ExtractionTask.model) gets its own client.

    Temperature defaults to 0 on purpose: structured extraction (pick codes from a closed
    candidate list) must be reproducible — run-to-run variance means the same transcript
    can non-reproducibly get a code or not, which undermines both debugging and the
    physician's trust in the suggestion."""
    return chat_provider().build(model, temperature)
