"""Unit tests for app/ramq_chatbot/manual_references.py — ManualSectionLookup is a thin
wrapper around BasePydanticVectorStore.get_nodes(filters=...), pinned here against a small
in-memory fake store rather than a real LanceDB table."""

from typing import Any, Optional

from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores.types import BasePydanticVectorStore, MetadataFilters

from app.ramq_chatbot.manual_references import ManualSectionLookup


class _FakeVectorStore(BasePydanticVectorStore):
    """Only implements what ManualSectionLookup actually calls: get_nodes(filters=...) with a
    single equality filter — enough to stand in for LanceDBVectorStore here without a real
    LanceDB table (LanceDBVectorStore._to_lance_filter's `metadata.<key>` prefixing is
    LanceDB-specific plumbing, not something ManualSectionLookup itself depends on)."""

    stores_text: bool = True
    _nodes: list[BaseNode] = PrivateAttr(default_factory=list)

    def __init__(self, nodes: list[BaseNode]):
        super().__init__()
        self._nodes = list(nodes)

    @property
    def client(self) -> None:
        return None

    def add(self, nodes: list[BaseNode], **kwargs: Any) -> list[str]:
        raise NotImplementedError

    def delete(self, ref_doc_id: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def query(self, *args: Any, **kwargs: Any):
        raise NotImplementedError

    def get_nodes(
        self, node_ids: Optional[list[str]] = None, filters: Optional[MetadataFilters] = None
    ) -> list[BaseNode]:
        assert filters is not None and len(filters.filters) == 1
        key, value = filters.filters[0].key, filters.filters[0].value
        return [n for n in self._nodes if n.metadata.get(key) == value]


def _node(node_id: str, metadata: dict) -> TextNode:
    return TextNode(text="", id_=node_id, metadata=metadata)


def test_returns_the_node_with_a_matching_section_number():
    match = _node("A", {"section_number": "2.2.6"})
    other = _node("B", {"section_number": "2.2.1"})
    lookup = ManualSectionLookup(_FakeVectorStore([match, other]))

    results = lookup.get_by_section_number("2.2.6")

    assert [n.node_id for n in results] == ["A"]


def test_returns_empty_list_when_no_node_matches():
    lookup = ManualSectionLookup(_FakeVectorStore([_node("A", {"section_number": "2.2.1"})]))

    assert lookup.get_by_section_number("9.9") == []


def test_returns_every_node_sharing_a_section_number():
    # OversizedNodeSplitter (ramq-ingestion) splits an oversized section into multiple nodes
    # that all inherit the same section_number verbatim — section_number is not unique.
    first_half = _node("A", {"section_number": "2.2.6"})
    second_half = _node("B", {"section_number": "2.2.6"})
    lookup = ManualSectionLookup(_FakeVectorStore([first_half, second_half]))

    results = lookup.get_by_section_number("2.2.6")

    assert {n.node_id for n in results} == {"A", "B"}


def test_a_node_with_no_section_number_metadata_is_never_matched():
    lookup = ManualSectionLookup(_FakeVectorStore([_node("A", {})]))

    assert lookup.get_by_section_number("2.2.6") == []
