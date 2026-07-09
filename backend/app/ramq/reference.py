"""Loads the RAMQ code reference table and narrows it down to candidates for a transcript.

The reference file shipped in this repo (reference_data.json) is placeholder data — see the
"_warning" field in that file. Swap it for the real RAMQ nomenclature before using this for
anything other than pipeline development.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REFERENCE_PATH = Path(__file__).parent / "reference_data.json"


@dataclass(frozen=True)
class RamqCode:
    code: str
    description: str
    category: str
    keywords: tuple[str, ...]
    # Flat fee only for now — real RAMQ fees vary by modifiers (specialist vs. GP, time of
    # day/weekend, region, act complexity) that aren't modeled yet. See _pricing_note in
    # reference_data.json. None if a source entry doesn't have pricing yet.
    price_cad: float | None = None


class RamqReferenceTable:
    def __init__(self, codes: list[RamqCode]):
        self._codes = codes
        self._by_code = {c.code: c for c in codes}

    @classmethod
    def load(cls, path: Path = REFERENCE_PATH) -> "RamqReferenceTable":
        data = json.loads(path.read_text())
        codes = [
            RamqCode(
                code=entry["code"],
                description=entry["description"],
                category=entry["category"],
                keywords=tuple(entry.get("keywords", [])),
                price_cad=entry.get("price_cad"),
            )
            for entry in data["codes"]
        ]
        return cls(codes)

    def all_codes(self) -> list[RamqCode]:
        return list(self._codes)

    def get(self, code: str) -> RamqCode | None:
        return self._by_code.get(code)

    def candidates_for(self, transcript: str, limit: int = 25) -> list[RamqCode]:
        """Keyword-match candidates for a transcript.

        This is intentionally simple (substring matching, not embeddings) — once the real
        RAMQ table has thousands of entries, replace this with proper retrieval (e.g. a
        vector index over code descriptions). For now it keeps the candidate list small
        enough to fit in the LLM prompt and gives the model a closed set to choose from
        instead of relying on its own recall of RAMQ codes.
        """
        text = transcript.lower()
        scored: list[tuple[int, RamqCode]] = []
        for entry in self._codes:
            score = sum(1 for kw in entry.keywords if re.search(re.escape(kw.lower()), text))
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        candidates = [entry for _, entry in scored[:limit]]
        # Fall back to the full table if nothing matched, so the model still has options
        # to reason about rather than an empty candidate list.
        return candidates or self._codes[:limit]


@lru_cache(maxsize=1)
def get_reference_table() -> RamqReferenceTable:
    return RamqReferenceTable.load()
