"""Unit tests for RAMQManualRetriever (app/ramq_chatbot/retriever.py) — the BM25+vector
fusion retriever used by scripts/simple_query.py.

Note: app/ramq_chatbot is separate from, and not wired into, the actively-used
app/ramq_codes pipeline (see tests/test_ramq_codes_retriever.py) — it's only exercised
by that manual script. These tests exist to pin down its current wiring, not to certify
it for production use.

No network calls / real API keys: the vector store is an in-memory fake with precomputed
node embeddings (no embedding client involved), the injected embed_model is a deterministic
exact-text-lookup fake for the query side (mirrors tests/test_vector_retrieval.py's
_LookupEmbedding), and the injected llm is a fake standing in for the LLM that
QueryFusionRetriever calls to generate extra search queries (num_queries=3 in
RAMQManualRetriever means 2 extra queries are requested by default)."""

from typing import Any, Optional

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.base.llms.types import CompletionResponse, LLMMetadata
from llama_index.core.bridge.pydantic import Field, PrivateAttr
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.schema import BaseNode, NodeWithScore, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    MetadataFilters,
    VectorStoreQuery,
    VectorStoreQueryResult,
)
import pytest

from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_chatbot.retriever import RAMQManualRetriever
from app.ramq_codes.codes_data import CodesData


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _FakeVectorStore(BasePydanticVectorStore):
    """In-memory stand-in for the real LanceDBVectorStore: stores nodes directly (with
    precomputed .embedding vectors) and answers query() with plain cosine similarity, so
    RAMQManualRetriever's VectorStoreIndex.from_vector_store(...).as_retriever() has
    something real to search without a Lance dataset or embedding API call."""

    stores_text: bool = True
    _nodes: list[BaseNode] = PrivateAttr(default_factory=list)

    def __init__(self, nodes: list[BaseNode]):
        super().__init__()
        self._nodes = list(nodes)

    @property
    def client(self) -> None:
        return None

    def add(self, nodes: list[BaseNode], **kwargs: Any) -> list[str]:
        self._nodes.extend(nodes)
        return [n.node_id for n in nodes]

    def delete(self, ref_doc_id: str, **kwargs: Any) -> None:
        self._nodes = [n for n in self._nodes if n.ref_doc_id != ref_doc_id]

    def get_nodes(
        self, node_ids: Optional[list[str]] = None, filters: Optional[MetadataFilters] = None
    ) -> list[BaseNode]:
        # Minimal support for RAMQManualRetriever's real usage: ManualSectionLookup issues a
        # single equality filter on one metadata key.
        if filters is None:
            return list(self._nodes)
        key, value = filters.filters[0].key, filters.filters[0].value
        return [n for n in self._nodes if n.metadata.get(key) == value]

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        scored = sorted(
            ((n, _cosine(query.query_embedding, n.embedding)) for n in self._nodes),
            key=lambda pair: pair[1],
            reverse=True,
        )
        top = scored[: query.similarity_top_k]
        return VectorStoreQueryResult(
            nodes=[n for n, _ in top],
            similarities=[s for _, s in top],
            ids=[n.node_id for n, _ in top],
        )


class _LookupQueryEmbedding(BaseEmbedding):
    """Exact text->vector lookup for query embeddings, passed as RAMQManualRetriever's
    embed_model. Node embeddings are set directly on each TextNode (see _node()) rather than
    computed here, since _FakeVectorStore never calls back into an embedding model to embed
    text."""

    vectors: dict[str, list[float]]

    def __init__(self, vectors: dict[str, list[float]], **kwargs: Any):
        super().__init__(vectors=vectors, **kwargs)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self.vectors[query]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self.vectors[query]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self.vectors[text]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self.vectors[text]


class _NoOpQueryGenLLM(CustomLLM):
    """Stands in for RAMQManualRetriever's llm during query-fusion's generate-more-queries
    step. Returns an empty completion so QueryFusionRetriever parses zero extra queries and
    only ever searches the original query string — keeps fixtures from needing
    embedding-lookup entries for LLM-generated query text none of these tests control."""

    prompts: list[str] = Field(default_factory=list)

    @classmethod
    def class_name(cls) -> str:
        return "noop_query_gen_llm"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(is_chat_model=False)

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        self.prompts.append(prompt)
        return CompletionResponse(text="")

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        raise NotImplementedError


class _NoOpReferenceExpander:
    """Stands in for ReferenceExpander in tests that aren't about reference expansion — just
    passes hits through unchanged, so existing retrieval-ranking tests don't need reference
    metadata fixtures."""

    def expand(self, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        return nodes

    async def aexpand(self, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        return nodes


class _EmptyCodesTableReader:
    """Empty ITableReader stand-in for tests that only exercise section-reference expansion
    (ReferenceExpander.aexpand's code_references half is unreachable when no node carries any
    code_references metadata)."""

    async def get_all(self, ids: list[str]) -> list:
        return []


def _node(
    node_id: str, text: str, vectors: dict[str, list[float]], metadata: dict | None = None
) -> TextNode:
    node = TextNode(text=text, id_=node_id, metadata=metadata or {})
    node.embedding = vectors[text]
    return node


def _build_retriever(
    vectors: dict[str, list[float]],
    nodes: list[BaseNode],
    llm: CustomLLM | None = None,
    reference_expander=None,
) -> RAMQManualRetriever:
    return RAMQManualRetriever(
        vector_store=_FakeVectorStore(nodes),
        llm=llm or _NoOpQueryGenLLM(),
        embed_model=_LookupQueryEmbedding(vectors),
        reference_expander=reference_expander or _NoOpReferenceExpander(),
    )


def _build_reference_expander(nodes: list[BaseNode]) -> ReferenceExpander:
    from app.lancedb.converter import CodesRowConverter

    return ReferenceExpander(
        section_lookup=ManualSectionLookup(_FakeVectorStore(nodes)),
        codes_data=CodesData(_EmptyCodesTableReader(), CodesRowConverter()),
    )


async def test_aretrieve_delegates_to_the_inner_query_fusion_retriever():
    # app/ramq_chatbot/engine.py's acustom_query calls .aretrieve(), not .retrieve() — pin
    # that RAMQManualRetriever._aretrieve actually delegates to the inner
    # QueryFusionRetriever's own .aretrieve() (which fans the fused vector+BM25 queries out
    # concurrently) rather than silently falling back to BaseRetriever's default sync-under-
    # an-async-wrapper behavior.
    vectors = {
        "urgence de nuit": [1.0, 0.0],
        "consultation de routine": [0.0, 1.0],
    }
    node_a = _node("A", "urgence de nuit", vectors)
    node_b = _node("B", "consultation de routine", vectors)

    retriever = _build_retriever(vectors, [node_a, node_b])
    results = await retriever.aretrieve("urgence de nuit")

    assert results[0].node.node_id == "A"


def test_retrieve_ranks_best_semantic_and_lexical_match_first():
    vectors = {
        "urgence de nuit": [1.0, 0.0],
        "consultation de routine": [0.0, 1.0],
    }
    node_a = _node("A", "urgence de nuit", vectors)  # exact vector + term match
    node_b = _node("B", "consultation de routine", vectors)  # orthogonal vector, no term match

    retriever = _build_retriever(vectors, [node_a, node_b])
    results = retriever.retrieve("urgence de nuit")

    assert results[0].node.node_id == "A"


def test_raises_when_vector_store_has_no_nodes():
    # Current behavior, not a design goal: BM25Retriever.from_defaults(nodes=[]) rejects an
    # empty corpus outright, so RAMQManualRetriever's constructor fails fast rather than
    # returning an empty retriever.
    with pytest.raises(ValueError):
        _build_retriever({}, [])


def test_limits_direct_retrieval_results_to_similarity_top_k():
    # Pins the inner fusion retriever's own cap (similarity_top_k=20) — the no-op
    # ReferenceExpander here means RAMQManualRetriever.retrieve()'s output is exactly the
    # fusion retriever's, unaffected by expansion (see the reference-expansion tests below for
    # the additive-on-top-of-this-cap behavior).
    vectors = {f"code {i}": [1.0, float(i)] for i in range(22)}
    nodes = [_node(str(i), f"code {i}", vectors) for i in range(22)]

    retriever = _build_retriever(vectors, nodes)
    results = retriever.retrieve("code 0")

    assert len(results) <= 20


def test_passes_custom_query_gen_prompt_to_llm():
    # Regression guard: RAMQManualRetriever builds QueryFusionRetriever with its own
    # QUERY_GEN_PROMPT (French, Quebec-doctor-specific, "do not suggest billing codes") —
    # if that wiring were dropped, QueryFusionRetriever would silently fall back to its
    # generic English default prompt.
    vectors = {"urgence": [1.0, 0.0]}
    spy = _NoOpQueryGenLLM()

    retriever = _build_retriever(vectors, [_node("A", "urgence", vectors)], llm=spy)
    retriever.retrieve("urgence")

    assert len(spy.prompts) == 1
    prompt = spy.prompts[0]
    assert "doctors in Quebec, Canada" in prompt
    assert "Do not suggest any billing codes." in prompt
    assert "Query: urgence" in prompt


# -- reference expansion: RAMQManualRetriever wired with a real ReferenceExpander ----------
# (test_ramq_chatbot_reference_expansion.py covers ReferenceExpander's own algorithm in
# isolation; these tests only pin that RAMQManualRetriever actually wires it in.)


def test_retrieve_includes_section_referenced_by_a_top_hit_even_when_it_ranks_last():
    # 21 filler nodes plus a "target" whose vector is far outside the filler range: 22 nodes
    # total, one more than similarity_top_k=20, and target is the single farthest — the one
    # direct retrieval cuts (see test_limits_direct_retrieval_results_to_similarity_top_k).
    vectors = {f"code {i}": [1.0, float(i)] for i in range(21)}
    vectors["far"] = [1.0, 1000.0]
    nodes = [_node(str(i), f"code {i}", vectors) for i in range(21)]
    referenced = _node("target", "far", vectors, metadata={"section_number": "9.9"})
    nodes[0].metadata["section_references"] = ["9.9"]

    retriever = _build_retriever(
        vectors, [*nodes, referenced], reference_expander=_build_reference_expander([*nodes, referenced])
    )
    results = retriever.retrieve("code 0")

    assert "target" in {n.node.node_id for n in results}
    assert next(n for n in results if n.node.node_id == "target").node.metadata["is_expansion"] is True


def test_retrieve_does_not_crash_on_a_section_reference_with_no_match():
    vectors = {"urgence": [1.0, 0.0]}
    node = _node("A", "urgence", vectors, metadata={"section_references": ["9.9"]})

    retriever = _build_retriever(vectors, [node], reference_expander=_build_reference_expander([node]))
    results = retriever.retrieve("urgence")

    assert [n.node.node_id for n in results] == ["A"]


def test_retrieve_includes_every_node_sharing_a_referenced_section_number():
    # Same "farthest nodes get cut by the top-k cap" setup as the first test above, but with
    # two nodes sharing the referenced section_number (the OversizedNodeSplitter case) — both
    # must survive expansion, not just one.
    vectors = {f"code {i}": [1.0, float(i)] for i in range(20)}
    vectors["detail 1"] = [1.0, 1000.0]
    vectors["detail 2"] = [1.0, 1001.0]
    fillers = [_node(str(i), f"code {i}", vectors) for i in range(20)]
    fillers[0].metadata["section_references"] = ["9.9"]
    detail_1 = _node("B", "detail 1", vectors, metadata={"section_number": "9.9"})
    detail_2 = _node("C", "detail 2", vectors, metadata={"section_number": "9.9"})

    all_nodes = [*fillers, detail_1, detail_2]
    retriever = _build_retriever(vectors, all_nodes, reference_expander=_build_reference_expander(all_nodes))
    results = retriever.retrieve("code 0")

    node_ids = {n.node.node_id for n in results}
    assert {"B", "C"} <= node_ids


def test_retrieve_does_not_duplicate_a_reference_that_is_already_a_direct_hit():
    vectors = {"urgence": [1.0, 0.0], "detail": [0.9, 0.1]}
    origin = _node("A", "urgence", vectors, metadata={"section_references": ["9.9"]})
    detail = _node("B", "detail", vectors, metadata={"section_number": "9.9"})

    all_nodes = [origin, detail]
    retriever = _build_retriever(vectors, all_nodes, reference_expander=_build_reference_expander(all_nodes))
    results = retriever.retrieve("urgence")

    node_ids = [n.node.node_id for n in results]
    assert node_ids.count("B") == 1
