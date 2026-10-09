"""The contracts every chat-model and embedding-model backend implements. One subclass per
host family, so switching hosts (Mistral's API today, a Canadian-hosted vLLM/TGI/TEI
later — see docs/encounter-intake-plan.md §3–4) is a configuration change, never a
task-code change. Almost every host speaks the OpenAI wire protocol, so a provider mostly
decides the base URL and key app/llm/openai_client.py's clients are built with; Bedrock's
embeddings, which don't, have their own client (app/llm/bedrock.py)."""

from abc import ABC, abstractmethod

from app.llm.client import IChatClient, IEmbeddingClient


class ChatModelProvider(ABC):
    name: str

    @abstractmethod
    def build(self, model: str, temperature: float) -> IChatClient:
        """A chat client for `model`. Reads credentials/endpoint from `settings` at call
        time, never at construction (keeps tests' no_real_api_keys safety net)."""


class EmbeddingModelProvider(ABC):
    name: str

    @abstractmethod
    def build(self) -> IEmbeddingClient:
        """The embedding client retrieval embeds queries with. Reads credentials, endpoint
        and model name from `settings` at call time, like ChatModelProvider.build."""
