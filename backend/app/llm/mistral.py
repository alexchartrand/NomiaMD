from openai import AsyncOpenAI

from app.config import settings
from app.llm.client import IChatClient, IEmbeddingClient
from app.llm.openai_client import OpenAIChatClient, OpenAIEmbeddingClient
from app.llm.provider import ChatModelProvider, EmbeddingModelProvider

MISTRAL_API_ROOT = "https://api.mistral.ai"


def _base_url(endpoint: str | None) -> str:
    """Mistral's endpoint env vars name the server root, without `/v1` (the convention the
    Mistral SDK used); the OpenAI client wants the versioned base URL."""
    return (endpoint or MISTRAL_API_ROOT).rstrip("/") + "/v1"


class MistralChatProvider(ChatModelProvider):
    """Mistral's hosted API, through its OpenAI-compatible chat-completions endpoint
    (structured outputs included). LLM_ENDPOINT, when set, overrides the server root (no
    `/v1` suffix)."""

    name = "mistral"

    def build(self, model: str, temperature: float) -> IChatClient:
        client = AsyncOpenAI(base_url=_base_url(settings.llm_endpoint), api_key=settings.llm_api_key)
        return OpenAIChatClient(client, provider=self.name, model=model, temperature=temperature)


class MistralEmbeddingProvider(EmbeddingModelProvider):
    """Mistral's hosted embeddings API. EMBEDDING_MODEL (mistral-embed: the model
    ramq-ingestion embedded today's LanceDB tables with) and EMBEDDING_API_KEY are both
    required — checked here, since the OpenAI SDK would otherwise fall back to its own
    OPENAI_API_KEY variable. Always Mistral's own host: EMBEDDING_ENDPOINT is for
    openai_compatible only."""

    name = "mistral"

    def build(self) -> IEmbeddingClient:
        model = settings.embedding_model
        api_key = settings.embedding_api_key
        if not model or not api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=mistral requires EMBEDDING_API_KEY and EMBEDDING_MODEL (e.g. mistral-embed)")
        client = AsyncOpenAI(base_url=_base_url(None), api_key=api_key)
        return OpenAIEmbeddingClient(client, provider=self.name, model=model)
