"""Semantic candidate retrieval for RAMQ codes, backed by a llama_index VectorStoreIndex
over the LanceDB `codes` table at DB_PATH.

All llama_index types stay behind RamqVectorRetriever — billing_codes/task.py only ever sees
candidates_for()'s RamqCandidate objects, never a llama_index Node/Index/Retriever. That's
the seam meant to absorb a storage-backend change: swap the IVectorStore implementation
passed to load(), nothing else changes.

The LanceDB `codes` table is produced by the sibling repo `ramq-ingestion`
(~/Software/ramq-ingestion) — this backend has no code dependency on how it was built, only
on the table's metadata shape (number, description, when_to_use, rules, fees, confidence;
see that repo's src/models.py Code/Fee and src/embedding/code_node_builder.py). Nothing
here carries a structured eligibility tag beyond what's in `rules`/`fees`' free text.
"""

import os
from functools import lru_cache

from llama_index.core import VectorStoreIndex
from llama_index.core.indices.base import BaseIndex
from llama_index.embeddings.mistralai import MistralAIEmbedding

from app.ramq.models import Fee, RamqCandidate
from app.ramq.vector_store import IVectorStore, LanceVectorStore

__all__ = ["RamqCandidate", "RamqVectorRetriever", "get_vector_retriever"]

DEFAULT_TABLE_NAME = "codes"

# Must match whatever embedding model actually produced the vectors in the `codes` table —
# nothing in LanceDB records this itself, so this is an assertion, not something loaded from
# the data. Verified by smoke-testing a known query against a known expected code (see
# tests/test_vector_retrieval.py and scripts/ramq_vector_smoke_test.py) — a wrong model here
# would still load and query without error, just against numerically valid but semantically
# meaningless scores.
MISTRAL_EMBED_MODEL = "mistral-embed"

# Below this cosine-similarity score, a hit is noise rather than a real candidate — without
# this floor, an unrelated query still returns `limit` codes (whatever ranks least-badly),
# and billing_codes/task.py has no way to tell "no real candidate" from "weakest of a bad batch".
# Calibrated empirically against the previous corpus (relevant queries scored ~0.81-0.85 on-topic,
# an unrelated query topped out ~0.69) — needs revisiting against the current LanceDB corpus once
# a larger eval set is available, not a finished number.
MIN_SIMILARITY = 0.7


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


class RamqVectorRetriever:
    def __init__(self, index: BaseIndex):
        self._index = index

    @classmethod
    def load(
        cls,
        vector_store: IVectorStore | None = None,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> "RamqVectorRetriever":
        """Wraps the LanceDB `codes` table (or `table_name`, in a store other than the
        default DB_PATH-backed one) in a queryable llama_index index.

        Requires MISTRAL_API_KEY — raises if unset. There's no fallback/degraded mode for
        candidate retrieval; a missing key should fail loudly at first use, not silently
        return empty candidate lists.
        """
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY is required for RAMQ candidate retrieval (used to embed "
                "the query against the LanceDB codes table) — set it in .env."
            )
        store = vector_store or LanceVectorStore(persist_dir=os.environ["DB_PATH"])
        embed_model = MistralAIEmbedding(model_name=MISTRAL_EMBED_MODEL, api_key=api_key)
        index = VectorStoreIndex.from_vector_store(store.get_vector_store(table_name), embed_model=embed_model)
        return cls(index)

    def candidates_for(self, query: str, limit: int) -> list[RamqCandidate]:
        """Ranked RAMQ candidates (best first) for `query`, deduplicated by code, filtered
        to MIN_SIMILARITY."""
        retriever = self._index.as_retriever(similarity_top_k=limit)
        hits = retriever.retrieve(query)

        seen: set[str] = set()
        candidates: list[RamqCandidate] = []
        for hit in hits:
            if hit.score is not None and hit.score < MIN_SIMILARITY:
                continue
            number = hit.node.metadata.get("number")
            if not number or number in seen:
                continue
            seen.add(number)
            candidates.append(_candidate_from_metadata(number, hit.node.metadata))
        return candidates


@lru_cache(maxsize=1)
def get_vector_retriever() -> RamqVectorRetriever:
    return RamqVectorRetriever.load()
