"""Unit tests for app/ramq_chatbot/query_generator.py — LLMQueryGenerator mirrors
llama_index's QueryFusionRetriever._aget_queries (num_queries counts the *total* query
count including the original; num_queries<=1 skips the LLM call entirely), carved out into
its own class now that RAMQManualRetriever no longer wraps QueryFusionRetriever.

The injected llm is a spy CustomLLM, no network call / real API key needed."""

from typing import Any

from llama_index.core.base.llms.types import CompletionResponse, LLMMetadata
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.bridge.pydantic import Field

from app.ramq_chatbot.query_generator import LLMQueryGenerator


class _SpyLLM(CustomLLM):
    response_text: str = ""
    prompts: list[str] = Field(default_factory=list)

    @classmethod
    def class_name(cls) -> str:
        return "spy_llm"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(is_chat_model=False)

    async def acomplete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        self.prompts.append(prompt)
        return CompletionResponse(text=self.response_text)

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        raise NotImplementedError

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        raise NotImplementedError


async def test_num_queries_of_one_skips_the_llm_call_entirely():
    llm = _SpyLLM()
    generator = LLMQueryGenerator(llm)

    queries = await generator.agenerate("urgence de nuit", num_queries=1)

    assert queries == ["urgence de nuit"]
    assert llm.prompts == []


async def test_original_query_is_always_first_and_always_included():
    llm = _SpyLLM(response_text="requête générée un\nrequête générée deux")
    generator = LLMQueryGenerator(llm)

    queries = await generator.agenerate("urgence de nuit", num_queries=3)

    assert queries[0] == "urgence de nuit"
    assert queries == ["urgence de nuit", "requête générée un", "requête générée deux"]


async def test_generated_queries_are_split_on_newlines_and_blank_lines_dropped():
    llm = _SpyLLM(response_text="une\n\ndeux\n   \ntrois")
    generator = LLMQueryGenerator(llm)

    queries = await generator.agenerate("q", num_queries=4)

    assert queries == ["q", "une", "deux", "trois"]


async def test_more_generated_queries_than_requested_are_trimmed():
    llm = _SpyLLM(response_text="un\ndeux\ntrois\nquatre")
    generator = LLMQueryGenerator(llm)

    queries = await generator.agenerate("q", num_queries=2)

    # num_queries=2 means 1 extra generated query on top of the original.
    assert queries == ["q", "un"]


async def test_prompt_requests_num_queries_minus_one_and_is_french_medical_specific():
    llm = _SpyLLM(response_text="une")
    generator = LLMQueryGenerator(llm)

    await generator.agenerate("urgence", num_queries=3)

    [prompt] = llm.prompts
    assert "Generate 2 search queries" in prompt
    assert "Result must be in French." in prompt
    assert "Do not suggest any billing codes." in prompt
    assert "Query: urgence" in prompt


async def test_strips_surrounding_code_block_backticks():
    llm = _SpyLLM(response_text="`\nune\ndeux\n`")
    generator = LLMQueryGenerator(llm)

    queries = await generator.agenerate("q", num_queries=3)

    assert queries == ["q", "une", "deux"]
