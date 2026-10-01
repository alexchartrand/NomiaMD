from app.extraction.encounter_date import DateOrder
from app.intake.normalizers.base import NoteNormalizer
from app.intake.normalizers.html import HtmlNormalizer
from app.intake.normalizers.plain_text import PlainTextNormalizer


class NormalizerRegistry:
    """Which normalizer each `source_system` gets. A source nobody registered is treated as
    day-first plain text — what a Quebec physician pastes."""

    def __init__(self, default: NoteNormalizer | None = None) -> None:
        self._by_source: dict[str, NoteNormalizer] = {}
        self._default = default or PlainTextNormalizer()

    def register(self, source_system: str, normalizer: NoteNormalizer) -> None:
        self._by_source[source_system] = normalizer

    def for_source(self, source_system: str) -> NoteNormalizer:
        return self._by_source.get(source_system, self._default)


def default_normalizers() -> NormalizerRegistry:
    registry = NormalizerRegistry()
    # Epic (Santé Québec's DSN) is pasted as text until SMART on FHIR lands; its templates
    # are US-built and write month-first.
    registry.register("epic", PlainTextNormalizer(DateOrder.MDY))
    # The browser extension's DOM captures (step 13).
    for dme in ("omnimed", "medesync", "myle"):
        registry.register(dme, HtmlNormalizer())
    return registry
