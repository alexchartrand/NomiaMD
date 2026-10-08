"""Provider-agnostic chat (LLM_PROVIDER) and embedding (EMBEDDING_PROVIDER) clients, per-call
usage metering, and the startup embedding-dimension guard."""

from app.llm.chat import UnknownChatProviderError, chat_provider, get_chat_client
from app.llm.client import IChatClient, IEmbeddingClient
from app.llm.embedding_guard import EmbeddingDimensionGuard, EmbeddingDimensionMismatchError
from app.llm.embeddings import UnknownEmbeddingProviderError, embedding_provider, get_embedding_client
from app.llm.types import ChatMessage, ChatResult, TokenUsage
from app.llm.usage import LLMCallRecord, UsageRecorder, UsageScope, call_purpose, usage_scope

__all__ = [
    "get_chat_client",
    "chat_provider",
    "UnknownChatProviderError",
    "get_embedding_client",
    "embedding_provider",
    "UnknownEmbeddingProviderError",
    "EmbeddingDimensionGuard",
    "EmbeddingDimensionMismatchError",
    "IChatClient",
    "IEmbeddingClient",
    "ChatMessage",
    "ChatResult",
    "TokenUsage",
    "LLMCallRecord",
    "UsageRecorder",
    "UsageScope",
    "call_purpose",
    "usage_scope",
]
