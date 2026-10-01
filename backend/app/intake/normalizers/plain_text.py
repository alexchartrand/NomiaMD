from app.intake.normalizers.base import NoteNormalizer, tidy_whitespace


class PlainTextNormalizer(NoteNormalizer):
    """Pasted or pushed text: only whitespace is touched."""

    def normalize(self, raw: str) -> str:
        return tidy_whitespace(raw)
