import re
from html.parser import HTMLParser

from app.intake.normalizers.base import NoteNormalizer, tidy_whitespace

# Tags that end a paragraph, and tags that only end a line.
_PARAGRAPH_TAGS = frozenset({"p", "div", "section", "article", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"})
_LINE_TAGS = frozenset({"br", "li", "tr"})
# Never note content.
_SKIPPED_TAGS = frozenset({"script", "style", "head", "template"})
_WHITESPACE_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in _LINE_TAGS:
            self._parts.append("\n")
        elif tag in _PARAGRAPH_TAGS:
            self._parts.append("\n\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in _LINE_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _PARAGRAPH_TAGS:
            self._parts.append("\n\n")
        elif tag in ("td", "th"):
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            # Source line breaks are layout, not content — HTML renders them as spaces; only
            # the tags above break lines.
            self._parts.append(_WHITESPACE_RE.sub(" ", data))

    def text(self) -> str:
        return "".join(self._parts)


class HtmlNormalizer(NoteNormalizer):
    """A DOM capture (the browser extension) or an HTML document: tags are stripped,
    entities decoded, paragraph and line breaks kept."""

    def normalize(self, raw: str) -> str:
        extractor = _TextExtractor()
        extractor.feed(raw)
        extractor.close()
        lines = (" ".join(line.split()) for line in extractor.text().split("\n"))
        return tidy_whitespace("\n".join(lines))
