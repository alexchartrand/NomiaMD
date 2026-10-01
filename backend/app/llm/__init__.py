"""Provider-agnostic chat LLM (LLM_PROVIDER) and embedding model (EMBEDDING_PROVIDER)
construction, chat response reading, and the startup embedding-dimension guard."""

from app.llm.chat import UnknownChatProviderError, chat_provider, get_chat_llm
from app.llm.embedding_guard import EmbeddingDimensionGuard, EmbeddingDimensionMismatchError
from app.llm.embeddings import UnknownEmbeddingProviderError, embedding_provider, get_embedding_model
from app.llm.response import ChatCompletion, ChatResponseReader

__all__ = [
    "get_chat_llm",
    "chat_provider",
    "UnknownChatProviderError",
    "get_embedding_model",
    "embedding_provider",
    "UnknownEmbeddingProviderError",
    "EmbeddingDimensionGuard",
    "EmbeddingDimensionMismatchError",
    "ChatCompletion",
    "ChatResponseReader",
]
