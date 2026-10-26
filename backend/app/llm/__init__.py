"""Provider-agnostic chat (LLM_PROVIDER) and embedding (EMBEDDING_PROVIDER) clients, per-call
usage metering, the startup embedding-model guard, and the structured (JSON-schema) chat
call the summary and code-selection steps share."""

from app.llm.chat import UnknownChatProviderError, chat_provider, get_chat_client
from app.llm.client import IChatClient, IEmbeddingClient
from app.llm.embedding_guard import EmbeddingModelGuard, EmbeddingModelMismatchError, StoredEmbedding
from app.llm.embeddings import UnknownEmbeddingProviderError, embedding_provider, get_embedding_client
from app.llm.structured import ExtractionOutputError, StructuredChat, StructuredReply, resolve_model
from app.llm.types import ChatMessage, ChatResult, TokenUsage
from app.llm.usage import LLMCallRecord, UsageRecorder, UsageScope, call_purpose, usage_scope

__all__ = [
    "get_chat_client",
    "chat_provider",
    "UnknownChatProviderError",
    "get_embedding_client",
    "embedding_provider",
    "UnknownEmbeddingProviderError",
    "EmbeddingModelGuard",
    "EmbeddingModelMismatchError",
    "StoredEmbedding",
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
    "StructuredChat",
    "StructuredReply",
    "ExtractionOutputError",
    "resolve_model",
]
