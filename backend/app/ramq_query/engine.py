
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.llms import LLM
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.query_engine import CustomQueryEngine

from app.ramq_query.models import RAMQChatMessage

SYSTEM_PROMPT = """\
You are a RAMQ billing specialist.
Rules:
- Answer must be in french.
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


class RAMQManualQueryEngine(CustomQueryEngine):

    retriever: BaseRetriever
    llm: LLM

    def custom_query(self, query_str: str, chat_history: list[RAMQChatMessage] | None = None) -> str:
        nodes = self.retriever.retrieve(query_str)

        context_str = "\n\n".join([n.node.get_content() for n in nodes])

        messages = [ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT)]
        messages.extend(_to_chat_messages(chat_history or []))
        messages.append(
            ChatMessage(
                role=MessageRole.USER,
                content=USER_MESSAGE_TEMPLATE.format(context_str=context_str, query_str=query_str),
            )
        )

        response = self.llm.chat(messages)

        content = response.message.content
        if content is None:
            raise RuntimeError("Model returned an empty chat response")
        return content
