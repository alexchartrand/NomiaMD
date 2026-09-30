"""DocumentRow (a validated row of the `documents-embeddings` LanceDB table) -> the
llama_index TextNode the chatbot's retriever and engine work in."""

from llama_index.core.schema import TextNode

from app.lancedb.converter import IConverter
from app.lancedb.models import DocumentRow


class DocumentRowConverter(IConverter[DocumentRow, TextNode]):
    """DocumentRow -> TextNode, the shape ReferenceExpander/RAMQManualQueryEngine already
    read (section_number/page_start/page_end/section_references/code_references metadata —
    see reference_expansion.py and engine.py's _citation_prefix). Optional scalar columns
    absent on the row are omitted from metadata entirely (matches ramq-ingestion's own
    absent=NULL convention); the two reference-list columns default to [] rather than being
    omitted, since callers already read them via `.get(key, [])`."""

    def convert(self, data: DocumentRow) -> TextNode:
        metadata: dict = {
            "title": data.title,
            "url": data.url,
            "section_references": data.section_references or [],
            "code_references": data.code_references or [],
        }
        if data.section_number is not None:
            metadata["section_number"] = data.section_number
        if data.page_start is not None:
            metadata["page_start"] = data.page_start
        if data.page_end is not None:
            metadata["page_end"] = data.page_end

        return TextNode(id_=data.id, text=data.text, metadata=metadata)
