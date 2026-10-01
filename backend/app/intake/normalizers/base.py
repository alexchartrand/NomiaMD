"""A note's text arrives in its source's own shape (plain text, a DOM capture's HTML...).
Normalizing it first means the content hash — and so deduplication — compares what the
physician signed, not how it was transported."""

import re
from abc import ABC, abstractmethod

from app.extraction.encounter_date import DateOrder

_TRAILING_SPACE_RE = re.compile(r"[ \t ]+$", re.MULTILINE)
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def tidy_whitespace(text: str) -> str:
    """Unix line endings, no trailing spaces, at most one blank line in a row, no leading or
    trailing blank lines. Shared by every normalizer so equal notes hash equal."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACE_RE.sub("", text)
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text.strip()


class NoteNormalizer(ABC):
    def __init__(self, date_order: DateOrder = DateOrder.DMY) -> None:
        self._date_order = date_order

    @property
    def date_order(self) -> DateOrder:
        """How this source writes slash dates — passed to parse_encounter_date."""
        return self._date_order

    @abstractmethod
    def normalize(self, raw: str) -> str: ...
