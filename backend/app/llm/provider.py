"""The contracts every chat-model and embedding-model backend implements. One subclass per
wire protocol, so switching hosts (Mistral's API today, a Canadian-hosted vLLM/TGI/TEI
later — see docs/encounter-intake-plan.md §3–4) is a configuration change, never a
task-code change."""

from abc import ABC, abstractmethod

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM

# Applied by every provider: structured extraction outputs (the billing_codes JSON in
# particular) can be long, and a truncated completion is unparseable.
MAX_TOKENS = 4096


class ChatModelProvider(ABC):
    @abstractmethod
    def build(self, model: str, temperature: float) -> LLM:
        """A llama-index chat LLM for `model`. Reads credentials/endpoint from `settings`
        at call time, never at construction (keeps tests' no_real_api_keys safety net)."""


class EmbeddingModelProvider(ABC):
    @abstractmethod
    def build(self) -> BaseEmbedding:
        """The llama-index embedding model retrieval embeds queries with. Reads credentials,
        endpoint and model name from `settings` at call time, like ChatModelProvider.build."""
