"""Seam over the LanceDB directory RAMQ data is read from — mirrors ramq-ingestion's
src/embedding/code_table_writer.py (same persist_dir/table_name shape, this side only ever
reads). Kept separate from retriever.py so the DB backend can be swapped (or faked in tests)
without touching retrieval logic."""

from abc import ABC, abstractmethod

import lancedb


class ICodeTableReader(ABC):
    @abstractmethod
    def open_table(self, table_name: str) -> lancedb.table.Table:
        pass


class LanceCodeTableReader(ICodeTableReader):
    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir

    def open_table(self, table_name: str) -> lancedb.table.Table:
        return lancedb.connect(self.persist_dir).open_table(table_name)
