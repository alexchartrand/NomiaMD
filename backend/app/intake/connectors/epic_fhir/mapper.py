"""Epic FHIR resources → SourceNote. Pure: the reader fetches, this only reads structured
fields — identity, date, times, place and author come from the resources, never the text."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.clock import CLINIC_ZONE
from app.intake.channels import Channel
from app.intake.connectors.epic_fhir.client import Resource
from app.intake.connectors.epic_fhir.identifiers import PatientIdentifierStrategy
from app.intake.models import EncounterMeta, SourceNote

# The note body we read. Epic also offers RTF, which no normalizer handles.
NOTE_CONTENT_TYPE = "text/html"


class EpicNoteMapper:
    def __init__(
        self, identifiers: PatientIdentifierStrategy, source_system: str, zone: ZoneInfo = CLINIC_ZONE
    ) -> None:
        self._identifiers = identifiers
        self._source_system = source_system
        # Instants are stored as the clinic's wall-clock times.
        self._zone = zone

    @staticmethod
    def is_signed(document: Resource) -> bool:
        """A current, final note — not a draft (preliminary), nor one entered in error."""
        return document.get("status") == "current" and document.get("docStatus") == "final"

    @staticmethod
    def note_attachment(document: Resource) -> Resource | None:
        for content in document.get("content", []):
            attachment = content.get("attachment", {})
            if attachment.get("contentType", "").startswith(NOTE_CONTENT_TYPE) and attachment.get("url"):
                return attachment
        return None

    @staticmethod
    def encounter_reference(document: Resource) -> str | None:
        encounters = document.get("context", {}).get("encounter", [])
        return encounters[0].get("reference") if encounters else None

    def service_date(self, document: Resource, encounter: Resource | None) -> date | None:
        """The encounter's start, else the note's own clinical period, else its date."""
        start = self._start(document, encounter)
        return start.date() if isinstance(start, datetime) else start

    def to_source_note(
        self, document: Resource, text: str, patient: Resource, encounter: Resource | None
    ) -> SourceNote:
        time_start, time_end = self._times((encounter or {}).get("period", {}))
        return SourceNote(
            source_system=self._source_system,
            channel=Channel.FHIR_PULL,
            external_note_id=document["id"],
            external_encounter_id=(encounter or {}).get("id"),
            nam=self._identifiers.nam_for(patient),
            service_date=self.service_date(document, encounter),
            meta=EncounterMeta(
                time_start=time_start,
                time_end=time_end,
                location_label=_location(encounter),
                author_ref=_author(document),
                source_version=document.get("meta", {}).get("versionId"),
            ),
            text=text,
        )

    def _start(self, document: Resource, encounter: Resource | None) -> datetime | date | None:
        for raw in (
            (encounter or {}).get("period", {}).get("start"),
            document.get("context", {}).get("period", {}).get("start"),
            document.get("date"),
        ):
            parsed = self._parse(raw)
            if parsed is not None:
                return parsed
        return None

    def _times(self, period: Resource) -> tuple[time | None, time | None]:
        """The visit's start and end on the clinic's clock. A zero-length period is how Epic
        writes a date with no time (e.g. its sandbox's 05:00Z, Central midnight): it gives
        the date only, never an invented 01:00–01:00 visit."""
        start, end = period.get("start"), period.get("end")
        if start is not None and start == end:
            return None, None
        return self._time(start), self._time(end)

    def _time(self, raw: str | None) -> time | None:
        parsed = self._parse(raw)
        return parsed.time() if isinstance(parsed, datetime) else None

    def _parse(self, raw: str | None) -> datetime | date | None:
        """A FHIR dateTime: a full instant is moved to the clinic's zone; a bare date (no
        time) stays a date, so no time is invented for it."""
        if not raw:
            return None
        if "T" not in raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(self._zone) if parsed.tzinfo else parsed


def _location(encounter: Resource | None) -> str | None:
    for entry in (encounter or {}).get("location", []):
        display = entry.get("location", {}).get("display")
        if display:
            return display
    return None


def _author(document: Resource) -> str | None:
    authors = document.get("author", [])
    if not authors:
        return None
    return authors[0].get("reference") or authors[0].get("display")
