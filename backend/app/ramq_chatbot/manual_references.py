from llama_index.core.schema import TextNode

from app.lancedb.converter import IConverter
from app.lancedb.repository import IDocumentRepository


class ManualSectionLookup:
    """Resolves a manual section number (e.g. "2.2.6", parsed by ramq-ingestion out of a
    chunk's own prose as `section_references` metadata) to the documents-embeddings row(s)
    whose own `section_number` column matches it, converted to a TextNode. Async-only:
    IDocumentRepository has no sync query path (see app/lancedb/repository.py)."""

    def __init__(self, documents: IDocumentRepository, converter: IConverter):
        self._documents = documents
        self._converter = converter

    async def aget_by_section_number(self, section_number: str) -> list[TextNode]:
        rows = await self._documents.get_by_section_number(section_number)
        return [self._converter.convert(row) for row in rows]
