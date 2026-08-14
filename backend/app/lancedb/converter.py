from abc import ABC, abstractmethod
from pydantic import BaseModel
from app.lancedb.models import CodeRow
from app.ramq_codes.models import Code, CodeFee

class IConverter(ABC):
    @abstractmethod
    def convert(self, data: BaseModel) -> ...:
        pass

class CodesRowConverter(IConverter):
    def convert(self, data: CodeRow) -> Code:
        return Code(
            number=data.number,
            description=data.description,
            confidence=data.confidence,
            when_to_use=tuple(data.when_to_use),
            rules=tuple(data.rules),
            fees=tuple(
                CodeFee(amount=fee.amount, when_to_use=fee.when_to_use, majoration=fee.majoration)
                for fee in data.fees
            ),
        )