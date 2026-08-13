"""Seam over the LanceDB directory RAMQ data is read from — mirrors ramq-ingestion's
src/embedding/vector_store.py + lancedb_vector_store.py exactly (same interface, this side
only ever reads). Kept separate from retriever.py so the DB backend can be swapped
(or faked in tests) without touching retrieval logic."""

from abc import ABC, abstractmethod

from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.vector_stores.lancedb import LanceDBVectorStore


class IVectorStore(ABC):
    @abstractmethod
    def get_vector_store(self, table_name: str) -> BasePydanticVectorStore:
        pass


class LanceVectorStore(IVectorStore):
    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir

    def get_vector_store(self, table_name: str) -> LanceDBVectorStore:
        # flat_metadata=False: RAMQ code metadata carries nested fields (when_to_use, rules,
        # fees) — llama_index's default flat_metadata=True rejects any non-str/int/float/None
        # metadata value. Must match what the table was written with (see ramq-ingestion's
        # LanceVectorStore, which writes with the same flag).
        return LanceDBVectorStore(uri=self.persist_dir, table_name=table_name, flat_metadata=False)
