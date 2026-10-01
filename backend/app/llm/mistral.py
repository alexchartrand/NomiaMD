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
            api_key=settings.mistral_api_key,
            endpoint=settings.llm_endpoint,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
        )


class MistralEmbeddingProvider(EmbeddingModelProvider):
    """Mistral's hosted embeddings API, model from MISTRAL_EMBEDDING_MODEL — the model
    ramq-ingestion embedded today's LanceDB tables with."""

    def build(self) -> BaseEmbedding:
        return MistralAIEmbedding(
            model_name=settings.mistral_embedding_model,
            api_key=settings.mistral_api_key,
        )
