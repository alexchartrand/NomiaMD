from abc import ABC, abstractmethod

from llama_index.core.llms import LLM

# Carved out of llama_index.core.retrievers.fusion_retriever.QueryFusionRetriever, whose
# _aget_queries this mirrors — this backend no longer wraps QueryFusionRetriever (see
# retriever.py), but keeps its own fan-out query generation and this exact prompt.
# scripts/fake_llm_server.py matches requests against this prompt's fixed opening line
# (_RAMQ_CHATBOT_QUERY_GEN_MARKER) and expects a trailing "Query: {query}" line — both must
# stay verbatim.
QUERY_GEN_PROMPT = """
    You are a helpful assistant that generates multiple search queries based on a single input query.
    Queries will be used to retrieve billing information for doctors in Quebec, Canada.

    Generate {num_queries} search queries, one on each line,
    related to the following input query:
    Query: {query}

    Rules:
    - Result must be in French.
    - Use medical billing terminology, if possible.
    - Do not suggest any billing codes."""


class IQueryGenerator(ABC):
    @abstractmethod
    async def agenerate(self, query: str, num_queries: int) -> list[str]:
        pass


class LLMQueryGenerator(IQueryGenerator):
    """Fans one user query out into `num_queries` search queries via an LLM completion —
    the original query is always included, up front. `num_queries` follows
    QueryFusionRetriever's own convention: it's the *total* query count including the
    original, so num_queries=1 means "no fan-out" and skips the LLM call entirely."""

    def __init__(self, llm: LLM):
        self._llm = llm

    async def agenerate(self, query: str, num_queries: int) -> list[str]:
        if num_queries <= 1:
            return [query]

        prompt = QUERY_GEN_PROMPT.format(num_queries=num_queries - 1, query=query)
        response = await self._llm.acomplete(prompt)

        # Strip code block and assume the LLM properly put each query on its own line.
        generated = [line.strip() for line in response.text.strip("`").split("\n") if line.strip()]
        # The LLM often returns more queries than asked for, so trim the list.
        return [query, *generated[: num_queries - 1]]
