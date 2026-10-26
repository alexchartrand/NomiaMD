
import logging

from app.llm import ChatMessage, ChatResult, IChatClient, call_purpose
from app.ramq_chatbot.chunks import ScoredChunk
from app.ramq_chatbot.models import RAMQChatMessage
from app.ramq_chatbot.retriever import IManualRetriever

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a RAMQ billing specialist chatbot.
Rules:
- Answer must be in french.
- Answer must be in markdown.
- Answer will be aimed toward doctor in Quebec, Canada.
- Be concise in your answer, but give all the needed information to answer the query.
- If you don't have the information to answer, say it. Don't guess an answer.
- Users don't have access to the context, so be specific and do not refer to it in you answer.
- Cite source where you fond your information (manual, chapter, page if available).
"""

USER_MESSAGE_TEMPLATE = """\
Context information is below:
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {query_str}
"""

MAX_HISTORY_MESSAGES = 20


def _to_chat_messages(history: list[RAMQChatMessage]) -> list[ChatMessage]:
    return [ChatMessage(role=m.role, content=m.content) for m in history]


def _truncate_history(history: list[RAMQChatMessage]) -> list[RAMQChatMessage]:
    return history[-MAX_HISTORY_MESSAGES:]


def _build_messages(
    query_str: str, context_str: str, chat_history: list[RAMQChatMessage] | None
) -> list[ChatMessage]:
    messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
    messages.extend(_to_chat_messages(_truncate_history(chat_history or [])))
    messages.append(
        ChatMessage(
            role="user",
            content=USER_MESSAGE_TEMPLATE.format(context_str=context_str, query_str=query_str),
        )
    )
    return messages


def _citation_prefix(metadata: dict) -> str:
    """Builds a "[Section 2.2.6, p.14-16, https://...]"-style prefix from a chunk's metadata,
    so the model can follow the system prompt's "cite source" instruction. All fields
    optional. Chunks ReferenceExpander pulled in (metadata["is_expansion"]) get a distinct
    label. `url` (the source document's own link) is appended whenever present — unlike
    section/page, it isn't gated on section_number, since it's the only citation available
    for a chunk ramq-ingestion didn't tag with a section."""
    parts = []

    section = metadata.get("section_number")
    if section:
        label = "Section référencée" if metadata.get("is_expansion") else "Section"
        parts.append(f"{label} {section}")

        page_start = metadata.get("page_start")
        page_end = metadata.get("page_end")
        if page_start is not None:
            parts.append(f"p.{page_start}" if page_end in (None, page_start) else f"p.{page_start}-{page_end}")

    url = metadata.get("url")
    if url:
        parts.append(url)

    if not parts:
        return ""

    return f"[{', '.join(parts)}] "


def _format_context_entry(hit: ScoredChunk) -> str:
    return _citation_prefix(hit.chunk.metadata) + hit.chunk.text


def _extract_content(response: ChatResult) -> str:
    if response.content is None:
        raise RuntimeError("Model returned an empty chat response")
    return response.content


class RAMQManualQueryEngine:
    """Retrieves manual passages for a question, then has the chat model answer from them.
    Async-only, like its retriever. app/ramq_chatbot/router.py's POST /query is the only
    caller."""

    def __init__(self, retriever: IManualRetriever, chat_client: IChatClient):
        self.retriever = retriever
        self.chat_client = chat_client

    async def aquery(self, query: str, chat_history: list[RAMQChatMessage] | None = None) -> str:
        hits = await self.retriever.aretrieve(query)
        context_str = "\n\n".join(_format_context_entry(hit) for hit in hits)
        messages = _build_messages(query, context_str, chat_history)

        logger.debug("RAMQManualQueryEngine final query", extra={"user_message": messages[-1].content})

        # Latency and token usage are metered per call by the client itself (app/llm/usage.py).
        with call_purpose("ramq_chatbot"):
            response = await self.chat_client.chat(messages)

        return _extract_content(response)
