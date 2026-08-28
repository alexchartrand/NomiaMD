from llama_index.core.schema import BaseNode, NodeWithScore, TextNode

from app.ramq_chatbot.manual_references import ManualSectionLookup
from app.ramq_codes.codes_data import CodesData
from app.ramq_codes.models import Code

MAX_EXPANSION_NODES = 5


def _format_code_reference(code: Code) -> str:
    return f"{code.number}: {code.description}"


class ReferenceExpander:
    """Expands a retriever's raw hits with the manual sections/billing codes those hits'
    prose references (ramq-ingestion's `section_references`/`code_references` metadata).

    One-hop only: expansion nodes are never themselves re-scanned, so reference cycles can't
    loop and no cycle-detection is needed. Async-only: both collaborators need a running
    event loop (ManualSectionLookup's IDocumentRepository has no sync query path; CodesData
    never did either) — there's exactly one entry point, aexpand().
    """

    def __init__(
        self,
        section_lookup: ManualSectionLookup,
        codes_data: CodesData,
        max_expansions: int = MAX_EXPANSION_NODES,
    ):
        self._section_lookup = section_lookup
        self._codes_data = codes_data
        self._max_expansions = max_expansions

    async def aexpand(self, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        seen_node_ids = {n.node.node_id for n in nodes}
        expansions: list[NodeWithScore] = []
        budget = self._max_expansions

        for section_number in self._collect_references(nodes, "section_references"):
            if budget <= 0:
                break
            for referenced in await self._section_lookup.aget_by_section_number(section_number):
                if budget <= 0:
                    break
                if referenced.node_id in seen_node_ids:
                    continue
                expansions.append(self._tag_expansion(referenced, f"section {section_number} referenced"))
                seen_node_ids.add(referenced.node_id)
                budget -= 1

        if budget > 0:
            code_numbers = self._collect_references(nodes, "code_references")[:budget]
            codes = await self._codes_data.get(code_numbers)
            expansions.extend(
                self._tag_expansion(
                    TextNode(text=_format_code_reference(code)), f"code {code.number} referenced"
                )
                for code in codes
            )

        return [*nodes, *expansions]

    def _collect_references(self, nodes: list[NodeWithScore], metadata_key: str) -> list[str]:
        """Flat, order-preserving, deduped list of every value under `metadata_key` (e.g.
        "section_references"/"code_references") across all given nodes."""
        seen: set[str] = set()
        values: list[str] = []
        for n in nodes:
            for value in n.node.metadata.get(metadata_key, []):
                if value not in seen:
                    seen.add(value)
                    values.append(value)
        return values

    def _tag_expansion(self, node: BaseNode, reason: str) -> NodeWithScore:
        node.metadata["is_expansion"] = True
        node.metadata["expansion_reason"] = reason
        return NodeWithScore(node=node, score=None)
