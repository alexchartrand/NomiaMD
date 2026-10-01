"""One normalizer per source: raw note → the text that's hashed, stored and extracted, plus
the order that source writes dates in."""

from app.intake.normalizers.base import NoteNormalizer
from app.intake.normalizers.html import HtmlNormalizer
from app.intake.normalizers.plain_text import PlainTextNormalizer
from app.intake.normalizers.registry import NormalizerRegistry, default_normalizers

__all__ = ["HtmlNormalizer", "NormalizerRegistry", "NoteNormalizer", "PlainTextNormalizer", "default_normalizers"]
