"""What the physician typed in the code search box, and how it's searched: digits alone are
the start of a code number (every RAMQ code is five digits, "0070" means 00700-00709), and
anything else is a description searched through the French full-text index."""

import re
from dataclasses import dataclass
from enum import Enum

_NUMBER_PREFIX = re.compile(r"\d{1,5}")


class CodeQueryKind(str, Enum):
    EMPTY = "empty"
    NUMBER_PREFIX = "number_prefix"
    TEXT = "text"


@dataclass(frozen=True)
class CodeQuery:
    kind: CodeQueryKind
    value: str = ""


class CodeQueryParser:
    def parse(self, raw: str | None) -> CodeQuery:
        text = (raw or "").strip()
        if not text:
            return CodeQuery(CodeQueryKind.EMPTY)
        if _NUMBER_PREFIX.fullmatch(text):
            return CodeQuery(CodeQueryKind.NUMBER_PREFIX, text)
        return CodeQuery(CodeQueryKind.TEXT, text)
