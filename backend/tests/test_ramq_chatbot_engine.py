"""Unit tests for RAMQManualQueryEngine (app/ramq_chatbot/engine.py) — used by
RAMQManualRetriever (see test_ramq_chatbot_retriever.py) via app/ramq_chatbot/router.py's
POST /query. Async-only: RAMQManualRetriever has no sync query path (IDocumentRepository is
async-only), so custom_query() only exists to satisfy CustomQueryEngine's abstract method
and is expected to raise — acustom_query() is the only real entry point.

The retriever is stubbed with a deterministic fake (real BaseRetriever subclass, fixed
return nodes) and the injected llm is a spy that records the exact chat messages it was
called with and returns a canned response — no network call, no real API key needed."""

from typing import Any

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, LLMMetadata, MessageRole
from llama_index.core.bridge.pydantic import Field
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from app.ramq_chatbot.engine import MAX_HISTORY_MESSAGES, RAMQManualQueryEngine
from app.ramq_chatbot.models import RAMQChatMessage


class _StubRetriever(BaseRetriever):
    """Fixed-response BaseRetriever: RAMQManualQueryEngine.retriever is typed as
    BaseRetriever (a pydantic field), so a plain duck-typed stub won't pass validation —
    this is a real (minimal) subclass instead."""

    def __init__(self, nodes: list[NodeWithScore]):
        self._nodes = nodes
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._nodes


class _SpyLLM(CustomLLM):
    """Stands in for RAMQManualQueryEngine's llm: records every chat message list passed to
    achat() and always returns the same canned response, so tests can assert on both the
    messages RAMQManualQueryEngine built and the value it hands back unmodified."""

    response_text: str = "réponse factice"
    message_lists: list[list[ChatMessage]] = Field(default_factory=list)

    @classmethod
    def class_name(cls) -> str:
        return "spy_llm"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(is_chat_model=True)

    async def achat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        self.message_lists.append(list(messages))
        return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=self.response_text))

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        raise NotImplementedError

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        raise NotImplementedError

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        raise NotImplementedError


def _node(text: str) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text), score=1.0)


def _alternating_history(n: int) -> list[RAMQChatMessage]:
    """n messages alternating user/assistant, content tagged with its 0-based index so tests
    can assert exactly which ones survived truncation."""
    return [
        RAMQChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg-{i}")
        for i in range(n)
    ]


def test_custom_query_raises_not_implemented():
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([]), llm=_SpyLLM())

    with pytest.raises(NotImplementedError):
        engine.custom_query("Ma question")


async def test_acustom_query_joins_retrieved_node_texts_into_context():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Texte A"), _node("Texte B")]), llm=spy)

    await engine.acustom_query("Ma question")

    user_message = spy.message_lists[0][-1]
    assert user_message.role == MessageRole.USER
    assert "Texte A\n\nTexte B" in user_message.content


async def test_acustom_query_includes_query_str_and_rules():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)

    await engine.acustom_query("Quelle est la majoration de nuit?")

    messages = spy.message_lists[0]
    assert messages[0].role == MessageRole.SYSTEM
    assert "Answer must be in french." in messages[0].content
    assert "Query: Quelle est la majoration de nuit?" in messages[-1].content


async def test_acustom_query_returns_llm_response_unchanged():
    spy = _SpyLLM(response_text="27,25$ selon le manuel RAMQ")
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)

    response = await engine.acustom_query("Combien facturer?")

    assert response == "27,25$ selon le manuel RAMQ"


async def test_acustom_query_empty_retrieval_still_queries_llm_with_empty_context():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([]), llm=spy)

    await engine.acustom_query("Question sans contexte pertinent")

    assert len(spy.message_lists) == 1
    assert "---------------------\n\n---------------------\nGiven the context information" in spy.message_lists[0][-1].content


async def test_acustom_query_threads_chat_history_between_system_and_current_turn():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)
    history = [
        RAMQChatMessage(role="user", content="Quelle est la majoration de nuit?"),
        RAMQChatMessage(role="assistant", content="27,25$ selon le manuel RAMQ."),
    ]

    await engine.acustom_query("Et pour un enfant?", chat_history=history)

    messages = spy.message_lists[0]
    assert messages[0].role == MessageRole.SYSTEM
    assert messages[1].role == MessageRole.USER
    assert messages[1].content == "Quelle est la majoration de nuit?"
    assert messages[2].role == MessageRole.ASSISTANT
    assert messages[2].content == "27,25$ selon le manuel RAMQ."
    assert messages[3].role == MessageRole.USER
    assert "Query: Et pour un enfant?" in messages[3].content


async def test_acustom_query_truncates_chat_history_longer_than_cap_to_most_recent():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)
    history = _alternating_history(MAX_HISTORY_MESSAGES + 4)

    await engine.acustom_query("La suite?", chat_history=history)

    messages = spy.message_lists[0]
    threaded_history = messages[1:-1]  # strip leading SYSTEM and trailing current-turn USER
    assert len(threaded_history) == MAX_HISTORY_MESSAGES
    assert threaded_history[0].content == "msg-4"  # oldest 4 dropped
    assert threaded_history[-1].content == f"msg-{MAX_HISTORY_MESSAGES + 3}"  # most recent kept
    assert threaded_history[0].role == MessageRole.USER  # alternation preserved after slicing


async def test_acustom_query_chat_history_at_cap_is_not_truncated():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)
    history = _alternating_history(MAX_HISTORY_MESSAGES)

    await engine.acustom_query("La suite?", chat_history=history)

    threaded_history = spy.message_lists[0][1:-1]
    assert len(threaded_history) == MAX_HISTORY_MESSAGES
    assert threaded_history[0].content == "msg-0"


# -- citation prefixes (section/page metadata attached by ramq-ingestion, and by
# ReferenceExpander on reference-pulled-in nodes) ------------------------------------------


def _node_with_metadata(text: str, metadata: dict) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text, metadata=metadata), score=1.0)


async def test_context_entry_is_prefixed_with_section_and_page_when_present():
    spy = _SpyLLM()
    node = _node_with_metadata("Texte", {"section_number": "2.2.6", "page_start": 14, "page_end": 16})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), llm=spy)

    await engine.acustom_query("Ma question")

    context = spy.message_lists[0][-1].content
    assert "[Section 2.2.6, p.14-16] Texte" in context


async def test_context_entry_omits_page_range_when_page_start_equals_page_end():
    spy = _SpyLLM()
    node = _node_with_metadata("Texte", {"section_number": "2.2.6", "page_start": 14, "page_end": 14})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), llm=spy)

    await engine.acustom_query("Ma question")

    assert "[Section 2.2.6, p.14] Texte" in spy.message_lists[0][-1].content


async def test_expansion_node_gets_a_distinct_citation_label():
    spy = _SpyLLM()
    node = _node_with_metadata("Texte", {"section_number": "2.2.6", "is_expansion": True})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), llm=spy)

    await engine.acustom_query("Ma question")

    assert "[Section référencée 2.2.6] Texte" in spy.message_lists[0][-1].content


async def test_context_entry_with_no_metadata_falls_back_to_bare_text():
    # Regression guard: test_acustom_query_joins_retrieved_node_texts_into_context (above)
    # asserts the exact substring "Texte A\n\nTexte B" — a node with no citation metadata
    # must render unprefixed.
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Texte")]), llm=spy)

    await engine.acustom_query("Ma question")

    assert spy.message_lists[0][-1].content.count("[") == 0
