from abc import ABC, abstractmethod
from pydantic import BaseModel
from llama_index.core.schema import TextNode
from app.lancedb.models import CodeRow, DocumentRow
from app.ramq_codes.models import Code, CodeEligibility, CodeFee

class IConverter(ABC):
    @abstractmethod
    def convert(self, data: BaseModel) -> ...:
        pass

class CodesRowConverter(IConverter):
    def convert(self, data: CodeRow) -> Code:
        return Code(
            number=data.number,
            description=data.description,
            header_path=data.header_path,
            when_to_use=tuple(data.when_to_use),
            rules=tuple(data.rules),
            fees=tuple(
                CodeFee(
                    amount=fee.amount,
                    amount_text=fee.amount_text,
                    context=fee.context,
                    majoration=fee.majoration,
                    lieux=tuple(fee.lieux),
                    role=fee.role,
                    unit=fee.unit,
                )
                for fee in data.fees
            ),
            eligibility=CodeEligibility(
                min_age=data.min_age,
                max_age=data.max_age,
                min_panel_size=data.min_panel_size,
                max_panel_size=data.max_panel_size,
                requires_registered=data.requires_registered,
                requires_vulnerable=data.requires_vulnerable,
            ),
        )


class DocumentRowConverter(IConverter):
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