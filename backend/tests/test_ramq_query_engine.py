"""Unit tests for RAMQManualQueryEngine (app/ramq_query/engine.py) — pairs with
RAMQManualRetriever (see test_ramq_query_retriever.py) in scripts/simple_query.py; not part
of the actively-used app/ramq_codes pipeline (see app/ramq_codes/retriever.py).

The retriever is stubbed with a deterministic fake (real BaseRetriever subclass, fixed
return nodes) and the injected llm is a spy that records the exact prompt it was called with
and returns a canned response — no network call, no real API key needed."""

from typing import Any

from llama_index.core.base.llms.types import CompletionResponse, LLMMetadata
from llama_index.core.bridge.pydantic import Field
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from app.ramq_query.engine import RAMQManualQueryEngine


class _StubRetriever(BaseRetriever):
    """Fixed-response BaseRetriever: RAMQManualQueryEngine.retriever is typed as
    BaseRetriever (a pydantic field), so a plain duck-typed stub won't pass validation —
    this is a real (minimal) subclass instead."""

    def __init__(self, nodes: list[NodeWithScore]):
        self._nodes = nodes
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._nodes


class _SpyLLM(CustomLLM):
    """Stands in for RAMQManualQueryEngine's llm: records every prompt passed to complete()
    and always returns the same canned response, so tests can assert on both the prompt
    RAMQManualQueryEngine built and the value it hands back unmodified."""

    response_text: str = "réponse factice"
    prompts: list[str] = Field(default_factory=list)

    @classmethod
    def class_name(cls) -> str:
        return "spy_llm"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(is_chat_model=False)

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        self.prompts.append(prompt)
        return CompletionResponse(text=self.response_text)

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        raise NotImplementedError


def _node(text: str) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text), score=1.0)


def test_joins_retrieved_node_texts_into_context():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Texte A"), _node("Texte B")]), llm=spy)

    engine.query("Ma question")

    assert "Texte A\n\nTexte B" in spy.prompts[0]


def test_includes_query_str_and_qa_instructions_in_prompt():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)

    engine.query("Quelle est la majoration de nuit?")

    prompt = spy.prompts[0]
    assert "Query: Quelle est la majoration de nuit?" in prompt
    assert "Answer must be in french." in prompt


def test_returns_llm_response_unchanged():
    spy = _SpyLLM(response_text="27,25$ selon le manuel RAMQ")
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([_node("Contexte")]), llm=spy)

    response = engine.query("Combien facturer?")

    assert str(response) == "27,25$ selon le manuel RAMQ"


def test_empty_retrieval_still_queries_llm_with_empty_context():
    spy = _SpyLLM()
    engine = RAMQManualQueryEngine(retriever=_StubRetriever([]), llm=spy)

    engine.query("Question sans contexte pertinent")

    assert len(spy.prompts) == 1
    assert "---------------------\n\n---------------------\nGiven the context information" in spy.prompts[0]
