"""Notes the physician hands us by hand: pasted text, or a text file uploaded instead."""

from pathlib import PurePath

from app.care_setting import CareSetting
from app.intake.channels import Channel
from app.intake.connectors.nam_header import read_header_nam
from app.intake.connectors.splitter import NoteSplitter
from app.intake.models import EncounterMeta, SourceNote

_UPLOAD_SUFFIXES = frozenset({".txt", ".md"})


class UnsupportedUploadError(ValueError):
    """Not a file we read: only UTF-8 .txt/.md for now."""


class ManualConnector:
    def __init__(self, splitter: NoteSplitter | None = None) -> None:
        self._splitter = splitter or NoteSplitter()

    def from_paste(
        self,
        text: str,
        source_system: str,
        batch_label: str | None = None,
        care_setting: CareSetting | None = None,
    ) -> list[SourceNote]:
        """One SourceNote per note in the paste, all sharing `batch_label` (e.g. "Urgence
        2026-10-01 nuit") and `care_setting` — a pasted shift is all one place. An empty
        paste gives none."""
        return self._notes(text, source_system, batch_label, care_setting, Channel.PASTE)

    def from_upload(
        self,
        filename: str,
        content: bytes,
        source_system: str,
        batch_label: str | None = None,
        care_setting: CareSetting | None = None,
    ) -> list[SourceNote]:
        """An uploaded file, read as the same text a paste of it would be."""
        if PurePath(filename).suffix.lower() not in _UPLOAD_SUFFIXES:
            raise UnsupportedUploadError(f"Only {', '.join(sorted(_UPLOAD_SUFFIXES))} files are accepted")
        try:
            # utf-8-sig: Windows editors (Notepad) prepend a BOM.
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise UnsupportedUploadError("The file isn't UTF-8 text") from error
        return self._notes(text, source_system, batch_label, care_setting, Channel.UPLOAD)

    def _notes(
        self,
        text: str,
        source_system: str,
        batch_label: str | None,
        care_setting: CareSetting | None,
        channel: Channel,
    ) -> list[SourceNote]:
        return [
            SourceNote(
                source_system=source_system,
                channel=channel,
                nam=read_header_nam(piece),
                meta=EncounterMeta(care_setting=care_setting),
                text=piece,
                batch_label=batch_label,
            )
            for piece in self._splitter.split(text)
        ]
