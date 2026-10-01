"""Cuts one paste into one piece per note, so a physician can paste a whole ER shift at once."""

import re

from app.intake.connectors.nam_header import NAM_HEADER_RE

_SEPARATOR_RE = re.compile(r"^[ \t]*-{3,}[ \t]*$", re.MULTILINE)


class NoteSplitter:
    """Two boundaries, both recognizable without reading the note:

    - an explicit separator line (`---`), which always cuts — including a Markdown rule
      inside a note, so a single note with one is pasted on its own;
    - a header block (a paragraph) with a NAM line, once the current piece already has
      one. The cut is at the start of that paragraph, so the lines above the NAM in the
      same header (clinic, physician, patient) stay with their note.

    Blank pieces are dropped; the rest are returned stripped, in paste order."""

    def split(self, text: str) -> list[str]:
        pieces: list[str] = []
        for chunk in _SEPARATOR_RE.split(text):
            pieces.extend(self._split_on_nam_headers(chunk))
        return [piece for piece in (p.strip() for p in pieces) if piece]

    def _split_on_nam_headers(self, chunk: str) -> list[str]:
        pieces: list[list[str]] = [[]]
        has_nam = False
        for paragraph in _paragraphs(chunk):
            starts_note = NAM_HEADER_RE.search(paragraph) is not None
            if starts_note and has_nam:
                pieces.append([])
            has_nam = has_nam or starts_note
            pieces[-1].append(paragraph)
        return ["\n\n".join(piece) for piece in pieces]


def _paragraphs(chunk: str) -> list[str]:
    """Runs of non-blank lines — blank-line spacing is the normalizer's business."""
    paragraphs: list[list[str]] = [[]]
    for line in chunk.splitlines():
        if line.strip():
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])
    return ["\n".join(lines) for lines in paragraphs if lines]
