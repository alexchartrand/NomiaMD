from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.embeddings.mistralai import MistralAIEmbedding
from llama_index.llms.mistralai import MistralAI

from app.config import settings
from app.llm.provider import MAX_TOKENS, ChatModelProvider, EmbeddingModelProvider


class MistralChatProvider(ChatModelProvider):
    """Mistral's hosted API. LLM_ENDPOINT, when set, overrides the server root (no `/v1`
    suffix — the Mistral SDK appends it); unset falls back to the SDK's default (which also
    still honours MISTRAL_ENDPOINT)."""

    def build(self, model: str, temperature: float) -> LLM:
        return MistralAI(
            model=model,
            api_key=settings.llm_api_key,
            endpoint=settings.llm_endpoint,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
        )


class MistralEmbeddingProvider(EmbeddingModelProvider):
    """Mistral's hosted embeddings API. EMBEDDING_MODEL (mistral-embed: the model
    ramq-ingestion embedded today's LanceDB tables with) and EMBEDDING_API_KEY are both
    required — checked here, since the Mistral SDK would otherwise fall back to its own
    MISTRAL_API_KEY variable."""

    def build(self) -> BaseEmbedding:
        model = settings.embedding_model
        api_key = settings.embedding_api_key
        if not model or not api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=mistral requires EMBEDDING_API_KEY and EMBEDDING_MODEL (e.g. mistral-embed)")
        return MistralAIEmbedding(model_name=model, api_key=api_key)
