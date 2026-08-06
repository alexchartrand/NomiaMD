"""Semantic candidate retrieval for RAMQ codes, backed by a llama_index VectorStoreIndex.

All llama_index types stay behind RamqVectorRetriever — reference.py and billing_codes.py
only ever see candidates_for()'s bare code strings, never a llama_index Node/Index/Retriever.
That's the seam meant to absorb a future storage-backend change: the index is persisted
locally today (app/ramq/vector/, a llama_index SimpleVectorStore/StorageContext dump built
from test_llama_result.json) and is expected to move to a real database later — when that
happens, only load()'s body changes, not this class's public shape or any caller.
"""

import os
from functools import lru_cache
from pathlib import Path

from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.indices.base import BaseIndex
from llama_index.embeddings.mistralai import MistralAIEmbedding

VECTOR_STORE_DIR = Path(__file__).parent / "vector"

# Must match whatever embedding model actually produced the vectors persisted under
# VECTOR_STORE_DIR — nothing in that persisted store records this itself (llama_index's
# local StorageContext dump doesn't carry embedding-model provenance), so this is an
# assertion, not something loaded from the data. Verified by smoke-testing a known query
# against a known expected code (see tests/test_vector_retrieval.py and scripts/
# ramq_vector_smoke_test.py) — a wrong model here would still load and query without error,
# just against numerically valid but semantically meaningless scores.
MISTRAL_EMBED_MODEL = "mistral-embed"

# Below this cosine-similarity score, a hit is noise rather than a real candidate — without
# this floor, an unrelated query still returns `limit` codes (whatever ranks least-badly),
# and billing_codes.py has no way to tell "no real candidate" from "weakest of a bad batch".
# Calibrated empirically against this corpus (relevant queries scored ~0.81-0.85 on-topic,
# an unrelated query topped out ~0.69) — needs revisiting once a larger eval set is
# available, not a finished number.
MIN_SIMILARITY = 0.75


class RamqVectorRetriever:
    def __init__(self, index: BaseIndex):
        self._index = index

    @classmethod
    def load(cls, persist_dir: Path | None = None) -> "RamqVectorRetriever":
        """Loads the persisted llama_index StorageContext and wraps it in a queryable index.

        `persist_dir` is resolved here rather than bound as a default argument value, same
        reasoning as REFERENCE_PATH in reference.py: a default is bound once at def time, so
        monkeypatching VECTOR_STORE_DIR in tests wouldn't take effect otherwise.

        Requires MISTRAL_API_KEY — raises if unset. There's no fallback/degraded mode for
        candidate retrieval anymore; a missing key should fail loudly at first use, not
        silently return empty candidate lists.
        """
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY is required for RAMQ candidate retrieval (used to embed "
                "the query against the app/ramq/vector/ corpus) — set it in .env."
            )
        storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir or VECTOR_STORE_DIR))
        embed_model = MistralAIEmbedding(model_name=MISTRAL_EMBED_MODEL, api_key=api_key)
        index = load_index_from_storage(storage_context, embed_model=embed_model)
        return cls(index)

    def candidates_for(self, query: str, limit: int) -> list[str]:
        """Ranked RAMQ code numbers (best first) for `query`, deduplicated, filtered to
        MIN_SIMILARITY. Returns bare code strings, not RamqCode — mapping to the full
        reference table (and dropping any code this corpus doesn't share with it) is
        reference.py's job, not this class's."""
        retriever = self._index.as_retriever(similarity_top_k=limit)
        hits = retriever.retrieve(query)

        seen: set[str] = set()
        codes: list[str] = []
        for hit in hits:
            if hit.score is not None and hit.score < MIN_SIMILARITY:
                continue
            number = hit.node.metadata.get("number")
            if not number or number in seen:
                continue
            seen.add(number)
            codes.append(number)
        return codes


@lru_cache(maxsize=1)
def get_vector_retriever() -> RamqVectorRetriever:
    return RamqVectorRetriever.load()
