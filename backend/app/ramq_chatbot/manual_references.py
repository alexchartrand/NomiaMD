from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)


class ManualSectionLookup:
    """Resolves a manual section number (e.g. "2.2.6", parsed by ramq-ingestion out of a
    chunk's own prose as `section_references` metadata) to the documents-embeddings node(s)
    whose own `section_number` metadata matches it. Reuses RAMQManualRetriever's own
    LanceDBVectorStore rather than opening a second connection."""

    def __init__(self, vector_store: BasePydanticVectorStore):
        self._vector_store = vector_store

    def get_by_section_number(self, section_number: str) -> list[BaseNode]:
        filters = MetadataFilters(
            filters=[
                MetadataFilter(key="section_number", value=section_number, operator=FilterOperator.EQ)
            ]
        )
        return self._vector_store.get_nodes(filters=filters)
