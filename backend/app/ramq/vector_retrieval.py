"""Semantic candidate retrieval for RAMQ codes, backed by a llama_index VectorStoreIndex
over the LanceDB `codes` table at DB_PATH.

All llama_index types stay behind RAMQCodesRetriever/candidates_from_nodes —
billing_codes/task.py only ever sees RamqCandidate objects, never a llama_index
Node/Index/Retriever directly.

The LanceDB `codes` table is produced by the sibling repo `ramq-ingestion`
(~/Software/ramq-ingestion) — this backend has no code dependency on how it was built, only
on the table's metadata shape (number, description, when_to_use, rules, fees, confidence;
see that repo's src/models.py Code/Fee and src/embedding/code_node_builder.py). Nothing
here carries a structured eligibility tag beyond what's in `rules`/`fees`' free text.
"""

import os
from functools import lru_cache
from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.vector_stores.types import BasePydanticVectorStore

from app.ramq.models import Fee, RamqCandidate
from app.ramq.vector_store import LanceVectorStore
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
    def __init__(self, vector_store: BasePydanticVectorStore, embed_model: BaseEmbedding):
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
        self._retriever = index.as_retriever(similarity_top_k=30)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._retriever.retrieve(query_bundle)


@lru_cache(maxsize=1)
def get_ramq_retriever() -> RAMQCodesRetriever:
    """The BaseRetriever BillingCodesTask is constructed with (see app/tasks/registry.py)."""
    vector_store = LanceVectorStore(persist_dir=os.environ["DB_PATH"]).get_vector_store(DEFAULT_TABLE_NAME)
    return RAMQCodesRetriever(vector_store, get_embeding_model())
