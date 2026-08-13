"""Semantic candidate retrieval for RAMQ codes, backed by a direct LanceDB vector search over
the `codes` table at DB_PATH — RAMQCodesRetriever stays a llama_index BaseRetriever (so
task.py needs no changes) but no longer routes through VectorStoreIndex: it embeds the query
itself and calls `table.search(...)`, then wraps each flat result row in a TextNode so
candidates_from_nodes (unchanged) can keep reading it via `.metadata`.

All llama_index types stay behind RAMQCodesRetriever/candidates_from_nodes —
task.py (BillingCodesTask) only ever sees RamqCandidate objects, never a llama_index
Node/Index/Retriever directly.

The LanceDB `codes` table is produced by the sibling repo `ramq-ingestion`
(~/Software/ramq-ingestion) — this backend has no code dependency on how it was built, only
on the table's column shape (number, description, when_to_use, rules, fees, confidence, text,
vector; see that repo's src/models.py Code/Fee and src/embedding/code_record_builder.py).
Nothing here carries a structured eligibility tag beyond what's in `rules`/`fees`' free text.
"""

import os
from functools import lru_cache
from typing import List

import lancedb
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.core.base.embeddings.base import BaseEmbedding

from app.ramq_codes.models import Fee, RamqCandidate
from app.ramq_codes.vector_store import LanceCodeTableReader
from app.embedings import get_embeding_model

__all__ = ["RamqCandidate", "RAMQCodesRetriever", "get_ramq_retriever", "candidates_from_nodes"]

DEFAULT_TABLE_NAME = "codes"


def _fee_from_metadata(raw: dict) -> Fee:
    return Fee(amount=raw.get("amount"), when_to_use=raw.get("when_to_use"), majoration=raw.get("majoration"))


def _candidate_from_metadata(number: str, metadata: dict) -> RamqCandidate:
    return RamqCandidate(
        code=number,
        description=metadata.get("description", ""),
        when_to_use=tuple(metadata.get("when_to_use") or ()),
        rules=tuple(metadata.get("rules") or ()),
        fees=tuple(_fee_from_metadata(f) for f in metadata.get("fees") or ()),
    )

def candidates_from_nodes(nodes: list[NodeWithScore]) -> list[RamqCandidate]:
    return [
        _candidate_from_metadata(number, hit.node.metadata)
        for hit in nodes
        if (number := hit.node.metadata.get("number"))
    ]

class RAMQCodesRetriever(BaseRetriever):
    def __init__(self, table: lancedb.table.Table, embed_model: BaseEmbedding, similarity_top_k: int = 20):
        self._table = table
        self._embed_model = embed_model
        self._similarity_top_k = similarity_top_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_vector = self._embed_model.get_query_embedding(query_bundle.query_str)
        rows = (
            self._table.search(query_vector)
            .distance_type("cosine")
            .limit(self._similarity_top_k)
            .to_list()
        )
        return [
            NodeWithScore(node=TextNode(text=row.get("text", ""), metadata=row), score=1 - row["_distance"])
            for row in rows
        ]


@lru_cache(maxsize=1)
def get_ramq_retriever() -> RAMQCodesRetriever:
    """The BaseRetriever BillingCodesTask is constructed with (see app/tasks/registry.py)."""
    table = LanceCodeTableReader(persist_dir=os.environ["DB_PATH"]).open_table(DEFAULT_TABLE_NAME)
    return RAMQCodesRetriever(table, get_embeding_model())
