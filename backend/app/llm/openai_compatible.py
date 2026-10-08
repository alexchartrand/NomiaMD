from openai import AsyncOpenAI

from app.config import settings
from app.llm.client import IChatClient, IEmbeddingClient
from app.llm.openai_client import OpenAIChatClient, OpenAIEmbeddingClient
from app.llm.provider import ChatModelProvider, EmbeddingModelProvider


class OpenAICompatibleChatProvider(ChatModelProvider):
    """Any server speaking the OpenAI chat-completions protocol (vLLM, TGI, the fake dev
    server). LLM_ENDPOINT is the base URL *including* `/v1`, and is required here — there's
    no sensible default host. `response_format` (json_schema, strict) is forwarded to the
    request body as-is, which is OpenAI's own structured-output shape."""

    name = "openai_compatible"

    def build(self, model: str, temperature: float) -> IChatClient:
        endpoint = settings.llm_endpoint
        if not endpoint:
            raise RuntimeError("LLM_PROVIDER=openai_compatible requires LLM_ENDPOINT (e.g. http://host:8000/v1)")
        client = AsyncOpenAI(base_url=endpoint, api_key=settings.llm_api_key)
        return OpenAIChatClient(client, provider=self.name, model=model, temperature=temperature)


class OpenAICompatibleEmbeddingProvider(EmbeddingModelProvider):
    """Any server exposing OpenAI's `/v1/embeddings` (TEI, vLLM). EMBEDDING_ENDPOINT (base
    URL *including* `/v1`) and EMBEDDING_MODEL are both required — the model must be the one
    the LanceDB vectors were built with, which app/bootstrap.py checks by dimension."""

    name = "openai_compatible"

    def build(self) -> IEmbeddingClient:
        endpoint = settings.embedding_endpoint
        model = settings.embedding_model
        if not endpoint or not model:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai_compatible requires EMBEDDING_ENDPOINT "
                "(e.g. http://host:8080/v1) and EMBEDDING_MODEL"
            )
        # The OpenAI client needs some non-empty key even when the server has no auth.
        client = AsyncOpenAI(base_url=endpoint, api_key=settings.embedding_api_key or "unused")
        return OpenAIEmbeddingClient(client, provider=self.name, model=model)
