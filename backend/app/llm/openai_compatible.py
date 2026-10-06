from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.llms.openai_like import OpenAILike

from app.config import settings
from app.llm.provider import MAX_TOKENS, ChatModelProvider, EmbeddingModelProvider


class OpenAICompatibleChatProvider(ChatModelProvider):
    """Any server speaking the OpenAI chat-completions protocol (vLLM, TGI, the fake dev
    server). LLM_ENDPOINT is the base URL *including* `/v1`, and is required here — there's
    no sensible default host. `response_format` (json_schema, strict) is forwarded to the
    request body as-is, which is OpenAI's own structured-output shape."""

    def build(self, model: str, temperature: float) -> LLM:
        endpoint = settings.llm_endpoint
        if not endpoint:
            raise RuntimeError("LLM_PROVIDER=openai_compatible requires LLM_ENDPOINT (e.g. http://host:8000/v1)")
        return OpenAILike(
            model=model,
            api_base=endpoint,
            api_key=settings.llm_api_key,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
            is_chat_model=True,
            is_function_calling_model=False,
        )


class OpenAICompatibleEmbeddingProvider(EmbeddingModelProvider):
    """Any server exposing OpenAI's `/v1/embeddings` (TEI, vLLM). EMBEDDING_ENDPOINT (base
    URL *including* `/v1`) and EMBEDDING_MODEL are both required — the model must be the one
    the LanceDB vectors were built with, which app/bootstrap.py checks by dimension."""

    def build(self) -> BaseEmbedding:
        endpoint = settings.embedding_endpoint
        model = settings.embedding_model
        if not endpoint or not model:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai_compatible requires EMBEDDING_ENDPOINT "
                "(e.g. http://host:8080/v1) and EMBEDDING_MODEL"
            )
        return OpenAILikeEmbedding(
            model_name=model,
            api_base=endpoint,
            # The OpenAI client needs some non-empty value even when the server has no auth.
            api_key=settings.embedding_api_key or "unused",
        )
