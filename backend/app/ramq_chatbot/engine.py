
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from llama_index.core.llms import LLM
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.query_engine import CustomQueryEngine

from app.ramq_chatbot.models import RAMQChatMessage

SYSTEM_PROMPT = """\
You are a RAMQ billing specialist chatbot.
Rules:
- Answer must be in french.
- Answer will be aimed toward doctor in Quebec, Canada.
- Be concise in your answer.
- If you don't have the information to answer, say it. Don't guess an answer.
- Users don't have access to the context, so be specific and do not refer to it in you answer.
"""

USER_MESSAGE_TEMPLATE = """\
Context information is below:
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {query_str}
"""

_ROLE_MAP = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}


def _to_chat_messages(history: list[RAMQChatMessage]) -> list[ChatMessage]:
    return [ChatMessage(role=_ROLE_MAP[m.role], content=m.content) for m in history]


def _build_messages(
    query_str: str, context_str: str, chat_history: list[RAMQChatMessage] | None
) -> list[ChatMessage]:
    messages = [ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT)]
    messages.extend(_to_chat_messages(chat_history or []))
    messages.append(
        ChatMessage(
            role=MessageRole.USER,
            content=USER_MESSAGE_TEMPLATE.format(context_str=context_str, query_str=query_str),
        )
    )
    return messages


def _extract_content(response: ChatResponse) -> str:
    content = response.message.content
    if content is None:
        raise RuntimeError("Model returned an empty chat response")
    return content


class RAMQManualQueryEngine(CustomQueryEngine):

    retriever: BaseRetriever
    llm: LLM

    def custom_query(self, query_str: str, chat_history: list[RAMQChatMessage] | None = None) -> str:
        nodes = self.retriever.retrieve(query_str)
        context_str = "\n\n".join([n.node.get_content() for n in nodes])
        messages = _build_messages(query_str, context_str, chat_history)
        response = self.llm.chat(messages)
        return _extract_content(response)

    async def acustom_query(self, query_str: str, chat_history: list[RAMQChatMessage] | None = None) -> str:
        nodes = await self.retriever.aretrieve(query_str)
        context_str = "\n\n".join([n.node.get_content() for n in nodes])
        messages = _build_messages(query_str, context_str, chat_history)
        response = await self.llm.achat(messages)
        return _extract_content(response)
