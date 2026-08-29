"""Unit tests for app/ramq_chatbot/reference_expansion.py — ReferenceExpander turns a
retriever's raw hits into the hit list actually fed to the LLM by following each hit's
section_references/code_references metadata (ramq-ingestion's commit b0f7601) one hop deep.
Both collaborators (ManualSectionLookup, CodesData) are fakes here — this only pins
ReferenceExpander's own expansion/dedup/cap algorithm, not either collaborator's own lookup
logic (covered separately in test_ramq_chatbot_manual_references.py and
test_ramq_codes_codes_data.py). aexpand() is the only entry point — both collaborators are
async-only (IDocumentRepository has no sync query path), so there's no sync expand() to
test separately any more."""

from llama_index.core.schema import BaseNode, NodeWithScore, TextNode

from app.ramq_chatbot.reference_expansion import ReferenceExpander
from app.ramq_codes.models import Code


class _FakeSectionLookup:
    def __init__(self, nodes_by_section: dict[str, list[BaseNode]]):
        self._nodes_by_section = nodes_by_section
        self.calls: list[str] = []

    async def aget_by_section_number(self, section_number: str) -> list[BaseNode]:
        self.calls.append(section_number)
        return list(self._nodes_by_section.get(section_number, []))


class _FakeCodesData:
    def __init__(self, codes_by_number: dict[str, Code]):
        self._codes_by_number = codes_by_number
        self.get_calls: list[list[str]] = []

    async def get(self, numbers: list[str]) -> list[Code]:
        self.get_calls.append(list(numbers))
        return [self._codes_by_number[n] for n in numbers if n in self._codes_by_number]


def _hit(node_id: str, metadata: dict | None = None) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=f"text {node_id}", id_=node_id, metadata=metadata or {}), score=1.0)


def _plain_node(node_id: str, metadata: dict | None = None) -> TextNode:
    return TextNode(text=f"text {node_id}", id_=node_id, metadata=metadata or {})


def _code(number: str) -> Code:
    return Code(number=number, libelle=f"libelle {number}", description=f"description {number}")


async def test_aexpand_pulls_in_a_referenced_section():
    origin = _hit("A", {"section_references": ["9.9"]})
    referenced = _plain_node("B", {"section_number": "9.9"})
    expander = ReferenceExpander(_FakeSectionLookup({"9.9": [referenced]}), _FakeCodesData({}))

    results = await expander.aexpand([origin])

    node_ids = [n.node.node_id for n in results]
    assert node_ids == ["A", "B"]
    added = next(n for n in results if n.node.node_id == "B")
    assert added.node.metadata["is_expansion"] is True


async def test_aexpand_contributes_nothing_for_an_unresolvable_section_reference():
    origin = _hit("A", {"section_references": ["9.9"]})
    expander = ReferenceExpander(_FakeSectionLookup({}), _FakeCodesData({}))

    results = await expander.aexpand([origin])

    assert [n.node.node_id for n in results] == ["A"]


async def test_aexpand_includes_every_node_sharing_a_referenced_section_number():
    origin = _hit("A", {"section_references": ["9.9"]})
    first_half = _plain_node("B", {"section_number": "9.9"})
    second_half = _plain_node("C", {"section_number": "9.9"})
    expander = ReferenceExpander(_FakeSectionLookup({"9.9": [first_half, second_half]}), _FakeCodesData({}))

    results = await expander.aexpand([origin])

    assert {n.node.node_id for n in results} == {"A", "B", "C"}


async def test_aexpand_only_follows_one_hop():
    # B's own section_references (pointing at C) must never be read — only the original input
    # nodes are scanned for references.
    origin = _hit("A", {"section_references": ["9.9"]})
    referenced = _plain_node("B", {"section_number": "9.9", "section_references": ["1.1"]})
    chained = _plain_node("C", {"section_number": "1.1"})
    lookup = _FakeSectionLookup({"9.9": [referenced], "1.1": [chained]})
    expander = ReferenceExpander(lookup, _FakeCodesData({}))

    results = await expander.aexpand([origin])

    assert "C" not in {n.node.node_id for n in results}
    assert "1.1" not in lookup.calls


async def test_aexpand_does_not_duplicate_a_reference_already_among_the_input_nodes():
    already_present = _hit("B", {"section_number": "9.9"})
    origin = _hit("A", {"section_references": ["9.9"]})
    expander = ReferenceExpander(
        _FakeSectionLookup({"9.9": [already_present.node]}), _FakeCodesData({})
    )

    results = await expander.aexpand([origin, already_present])

    assert [n.node.node_id for n in results].count("B") == 1


async def test_aexpand_caps_total_expansions_and_never_drops_original_hits():
    origin = _hit("A", {"section_references": ["1", "2", "3"]})
    lookup = _FakeSectionLookup(
        {
            "1": [_plain_node("B", {"section_number": "1"})],
            "2": [_plain_node("C", {"section_number": "2"})],
            "3": [_plain_node("D", {"section_number": "3"})],
        }
    )
    expander = ReferenceExpander(lookup, _FakeCodesData({}), max_expansions=2)

    results = await expander.aexpand([origin])

    assert results[0].node.node_id == "A"
    assert len(results) == 1 + 2


async def test_aexpand_also_follows_code_references():
    origin = _hit("A", {"code_references": ["15801"]})
    codes_data = _FakeCodesData({"15801": _code("15801")})
    expander = ReferenceExpander(_FakeSectionLookup({}), codes_data)

    results = await expander.aexpand([origin])

    added = next(n for n in results if n.node.node_id != "A")
    assert added.node.metadata["is_expansion"] is True
    assert "15801" in added.node.get_content()


async def test_aexpand_silently_drops_an_unresolvable_code_reference():
    origin = _hit("A", {"code_references": ["15801"]})
    expander = ReferenceExpander(_FakeSectionLookup({}), _FakeCodesData({}))

    results = await expander.aexpand([origin])

    assert [n.node.node_id for n in results] == ["A"]


async def test_aexpand_requests_a_referenced_code_only_once_even_if_multiple_hits_cite_it():
    hit_1 = _hit("A", {"code_references": ["15801"]})
    hit_2 = _hit("B", {"code_references": ["15801"]})
    codes_data = _FakeCodesData({"15801": _code("15801")})
    expander = ReferenceExpander(_FakeSectionLookup({}), codes_data)

    results = await expander.aexpand([hit_1, hit_2])

    expansion_nodes = [n for n in results if n.node.node_id not in ("A", "B")]
    assert len(expansion_nodes) == 1
    assert codes_data.get_calls == [["15801"]]


async def test_aexpand_shares_its_budget_across_sections_and_codes():
    # Regression guard for the merge of the old sync expand() (sections) and aexpand()'s
    # extra code-reference hop into a single call — the code hop must still be skipped once
    # the section hop alone has exhausted the shared budget.
    origin = _hit("A", {"section_references": ["1"], "code_references": ["15801"]})
    lookup = _FakeSectionLookup({"1": [_plain_node("B", {"section_number": "1"})]})
    codes_data = _FakeCodesData({"15801": _code("15801")})
    expander = ReferenceExpander(lookup, codes_data, max_expansions=1)

    results = await expander.aexpand([origin])

    assert [n.node.node_id for n in results] == ["A", "B"]
    assert codes_data.get_calls == []
