"""The seam between a validated LanceDB row (models.py's CodeRow/DocumentRow) and whatever
shape a consumer works in. Only the interface lives here — each implementation lives with
the package whose shape it produces (app/ramq_codes/converter.py's CodesRowConverter,
app/ramq_chatbot/converter.py's DocumentRowConverter), so this package never imports the
domain packages built on top of it."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class IConverter(ABC, Generic[TIn, TOut]):
    @abstractmethod
    def convert(self, data: TIn) -> TOut:
        pass
