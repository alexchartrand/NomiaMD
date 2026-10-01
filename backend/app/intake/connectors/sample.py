"""The synthetic consultations/ notes, delivered the way a real source would deliver them."""

from collections.abc import Iterable

from app.intake.channels import Channel
from app.intake.models import SourceNote
from app.sample_patients import SamplePatient, get_sample_patients, parse_header_fields

# What the frontend sends as TranscriptSource.system for a simulated patient.
SAMPLE_SOURCE_SYSTEM = "simule"


class SampleConnector:
    def __init__(self, samples: Iterable[SamplePatient] | None = None) -> None:
        self._samples = samples

    def notes(self) -> list[SourceNote]:
        samples = get_sample_patients() if self._samples is None else self._samples
        return [self._note(sample) for sample in samples]

    @staticmethod
    def _note(sample: SamplePatient) -> SourceNote:
        fields = parse_header_fields(sample.transcript)
        return SourceNote(
            source_system=SAMPLE_SOURCE_SYSTEM,
            channel=Channel.SAMPLE,
            # The sample's dossier number stands in for a source system's note id.
            external_note_id=sample.id,
            # Both from the header lines: SamplePatient.nam is its **NAM :** line, normalized.
            nam=sample.nam,
            service_date=fields.get("Date/heure"),
            text=sample.transcript,
        )
