"""The chatbot's unit of retrieved context: a passage of the RAMQ manual (or a billing code
pulled in by reference expansion) plus the metadata its citation is built from."""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class ManualChunk:
    text: str
    # The documents-embeddings row id; a fresh one for a chunk that isn't a table row (a
    # code reference ReferenceExpander formats on the fly).
    id: str = field(default_factory=lambda: str(uuid4()))
    # section_number/page_start/page_end/url/title, the section_references/code_references
    # lists ReferenceExpander follows, and is_expansion/expansion_reason on expansions.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredChunk:
    chunk: ManualChunk
    # Not compared across queries; None for reference expansions.
    score: float | None = None
