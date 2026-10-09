"""Builds the configured query-embedding model. EMBEDDING_PROVIDER picks the backend; every
retriever (ramq_codes, ramq_chatbot) goes through get_embedding_client so none of them names
a provider. Query embeddings embed text derived from the transcript, so they carry PHI the
same way chat calls do (docs/encounter-intake-plan.md §3)."""

from functools import lru_cache

from app.config import settings
from app.llm.bedrock import BedrockEmbeddingProvider
from app.llm.client import IEmbeddingClient
from app.llm.mistral import MistralEmbeddingProvider
from app.llm.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.llm.provider import EmbeddingModelProvider

_PROVIDERS: dict[str, type[EmbeddingModelProvider]] = {
    "mistral": MistralEmbeddingProvider,
    "openai_compatible": OpenAICompatibleEmbeddingProvider,
    "bedrock": BedrockEmbeddingProvider,
}


class UnknownEmbeddingProviderError(ValueError):
    pass


def embedding_provider() -> EmbeddingModelProvider:
    name = settings.embedding_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownEmbeddingProviderError(
            f"Unknown EMBEDDING_PROVIDER={name!r}; expected one of {sorted(_PROVIDERS)}"
        ) from None


@lru_cache(maxsize=1)
def get_embedding_client() -> IEmbeddingClient:
    return embedding_provider().build()
