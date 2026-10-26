"""Unit tests for RAMQManualQueryEngine (app/ramq_chatbot/engine.py) — used by
RAMQManualRetriever (see test_ramq_chatbot_retriever.py) via app/ramq_chatbot/router.py's
POST /query.

The retriever is stubbed with a deterministic fake (fixed return chunks) and the injected
chat client is a spy that records the exact chat messages it was called with and returns a
canned response — no network call, no real API key needed."""

from collections.abc import Sequence
from typing import Any

from app.llm import ChatMessage, ChatResult, IChatClient, TokenUsage, usage_scope
from app.ramq_chatbot.chunks import ManualChunk, ScoredChunk
from app.ramq_chatbot.engine import MAX_HISTORY_MESSAGES, RAMQManualQueryEngine
from app.ramq_chatbot.models import RAMQChatMessage
from app.ramq_chatbot.retriever import IManualRetriever


class _StubRetriever(IManualRetriever):
    def __init__(self, hits: list[ScoredChunk]):
        self._hits = hits

    async def aretrieve(self, query: str) -> list[ScoredChunk]:
        return self._hits


class _SpyChatClient(IChatClient):
    """Stands in for RAMQManualQueryEngine's chat client: records every message list passed
    to chat() and always returns the same canned response, so tests can assert on both the
    messages RAMQManualQueryEngine built and the value it hands back unmodified."""

    model = "spy"

    def __init__(self, response_text: str = "réponse factice"):
        self.response_text = response_text
        self.message_lists: list[list[ChatMessage]] = []

    async def chat(self, messages: Sequence[ChatMessage], *, response_format: dict[str, Any] | None = None) -> ChatResult:
        self.message_lists.append(list(messages))
        return ChatResult(
            content=self.response_text, finish_reason="stop", model=self.model, usage=TokenUsage(), latency_ms=0.0
        )


def _node(text: str) -> ScoredChunk:
    return ScoredChunk(chunk=ManualChunk(text=text), score=1.0)


def _alternating_history(n: int) -> list[RAMQChatMessage]:
    """n messages alternating user/assistant, content tagged with its 0-based index so tests
    can assert exactly which ones survived truncation."""
    return [
        RAMQChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg-{i}")
        for i in range(n)
    ]


async def test_aquery_joins_retrieved_node_texts_into_context():
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Texte A"), _node("Texte B")]), chat_client=spy)

    await engine.aquery("Ma question")

    user_message = spy.message_lists[0][-1]
    assert user_message.role == "user"
    assert "Texte A\n\nTexte B" in user_message.content


async def test_aquery_includes_query_str_and_rules():
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), chat_client=spy)

    await engine.aquery("Quelle est la majoration de nuit?")

    messages = spy.message_lists[0]
    assert messages[0].role == "system"
    assert "Answer must be in french." in messages[0].content
    assert "Query: Quelle est la majoration de nuit?" in messages[-1].content


async def test_aquery_returns_llm_response_unchanged():
    spy = _SpyChatClient(response_text="27,25$ selon le manuel RAMQ")
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), chat_client=spy)

    response = await engine.aquery("Combien facturer?")

    assert response == "27,25$ selon le manuel RAMQ"


async def test_aquery_empty_retrieval_still_queries_llm_with_empty_context():
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([]), chat_client=spy)

    await engine.aquery("Question sans contexte pertinent")

    assert len(spy.message_lists) == 1
    assert "---------------------\n\n---------------------\nGiven the context information" in spy.message_lists[0][-1].content


async def test_aquery_threads_chat_history_between_system_and_current_turn():
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), chat_client=spy)
    history = [
        RAMQChatMessage(role="user", content="Quelle est la majoration de nuit?"),
        RAMQChatMessage(role="assistant", content="27,25$ selon le manuel RAMQ."),
    ]

    await engine.aquery("Et pour un enfant?", chat_history=history)

    messages = spy.message_lists[0]
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert messages[1].content == "Quelle est la majoration de nuit?"
    assert messages[2].role == "assistant"
    assert messages[2].content == "27,25$ selon le manuel RAMQ."
    assert messages[3].role == "user"
    assert "Query: Et pour un enfant?" in messages[3].content


async def test_aquery_truncates_chat_history_longer_than_cap_to_most_recent():
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), chat_client=spy)
    history = _alternating_history(MAX_HISTORY_MESSAGES + 4)

    await engine.aquery("La suite?", chat_history=history)

    messages = spy.message_lists[0]
    threaded_history = messages[1:-1]  # strip leading SYSTEM and trailing current-turn USER
    assert len(threaded_history) == MAX_HISTORY_MESSAGES
    assert threaded_history[0].content == "msg-4"  # oldest 4 dropped
    assert threaded_history[-1].content == f"msg-{MAX_HISTORY_MESSAGES + 3}"  # most recent kept
    assert threaded_history[0].role == "user"  # alternation preserved after slicing


async def test_aquery_chat_history_at_cap_is_not_truncated():
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), chat_client=spy)
    history = _alternating_history(MAX_HISTORY_MESSAGES)

    await engine.aquery("La suite?", chat_history=history)

    threaded_history = spy.message_lists[0][1:-1]
    assert len(threaded_history) == MAX_HISTORY_MESSAGES
    assert threaded_history[0].content == "msg-0"


# -- citation prefixes (section/page metadata attached by ramq-ingestion, and by
# ReferenceExpander on reference-pulled-in nodes) ------------------------------------------


def _node_with_metadata(text: str, metadata: dict) -> ScoredChunk:
    return ScoredChunk(chunk=ManualChunk(text=text, metadata=metadata), score=1.0)


async def test_context_entry_is_prefixed_with_section_and_page_when_present():
    spy = _SpyChatClient()
    node = _node_with_metadata("Texte", {"section_number": "2.2.6", "page_start": 14, "page_end": 16})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), chat_client=spy)

    await engine.aquery("Ma question")

    context = spy.message_lists[0][-1].content
    assert "[Section 2.2.6, p.14-16] Texte" in context


async def test_context_entry_omits_page_range_when_page_start_equals_page_end():
    spy = _SpyChatClient()
    node = _node_with_metadata("Texte", {"section_number": "2.2.6", "page_start": 14, "page_end": 14})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), chat_client=spy)

    await engine.aquery("Ma question")

    assert "[Section 2.2.6, p.14] Texte" in spy.message_lists[0][-1].content


async def test_expansion_node_gets_a_distinct_citation_label():
    spy = _SpyChatClient()
    node = _node_with_metadata("Texte", {"section_number": "2.2.6", "is_expansion": True})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), chat_client=spy)

    await engine.aquery("Ma question")

    assert "[Section référencée 2.2.6] Texte" in spy.message_lists[0][-1].content


async def test_context_entry_includes_url_alongside_section_and_page():
    spy = _SpyChatClient()
    node = _node_with_metadata(
        "Texte",
        {"section_number": "2.2.6", "page_start": 14, "url": "https://ramq.example/manuel#2.2.6"},
    )
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), chat_client=spy)

    await engine.aquery("Ma question")

    context = spy.message_lists[0][-1].content
    assert "[Section 2.2.6, p.14, https://ramq.example/manuel#2.2.6] Texte" in context


async def test_context_entry_falls_back_to_url_only_when_no_section_is_tagged():
    spy = _SpyChatClient()
    node = _node_with_metadata("Texte", {"url": "https://ramq.example/manuel"})
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([node]), chat_client=spy)

    await engine.aquery("Ma question")

    assert "[https://ramq.example/manuel] Texte" in spy.message_lists[0][-1].content


async def test_context_entry_with_no_metadata_falls_back_to_bare_text():
    # Regression guard: test_aquery_joins_retrieved_node_texts_into_context (above)
    # asserts the exact substring "Texte A\n\nTexte B" — a node with no citation metadata
    # must render unprefixed.
    spy = _SpyChatClient()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Texte")]), chat_client=spy)

    await engine.aquery("Ma question")

    assert spy.message_lists[0][-1].content.count("[") == 0


async def test_aquery_tags_its_chat_call_with_the_chatbot_purpose():
    # The spy doesn't record usage itself — only check the purpose is set around the call.
    from app.llm.usage import current_purpose

    seen: list[str | None] = []

    class _PurposeSpy(_SpyChatClient):
        async def chat(self, messages, *, response_format=None):
            seen.append(current_purpose())
            return await super().chat(messages, response_format=response_format)

    await RAMQManualQueryEngine(retriever=_StubRetriever([]), chat_client=_PurposeSpy()).aquery("Q")

    assert seen == ["ramq_chatbot"]
